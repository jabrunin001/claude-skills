#!/usr/bin/env python3
"""aws-guard: Claude Code PreToolUse hook for the Bash tool.

Pins every `aws` CLI call to a read-only profile (aws-expert-ro or
aws-expert-ro-<account>) and allowlists read verbs. A command word computed at
run time ($VAR, "$SHELL", $(...)) gets `ask`: the hook cannot see what runs.
Also denies inline AWS SDK code (python -c / node -e with boto3, botocore,
aws-sdk), curl --aws-sigv4, and AWS_* overrides on aws/terraform/cdk except
AWS_PROFILE=<read-only profile>.
Output: deny / ask as hookSpecificOutput JSON; allowed reads and other
commands print nothing, so the normal permission rules still decide.
Fails closed (deny) when a command that mentions aws cannot be parsed.
Standard library only, no network.  Self-test: python3 aws-guard.py --selftest
"""
import fnmatch
import json
import os
import re
import sys

PROFILE = "aws-expert-ro"
PROFILE_HINT = f"{PROFILE} or {PROFILE}-<account>"
PROFILE_RE = re.compile(r"^aws-expert-ro(-[A-Za-z0-9][A-Za-z0-9_.-]*)?$")
SUBST = "$(...)"  # marker left in a word where a substitution was removed
MAX_DEPTH = 8

SAFE_AWS_ENV = {"AWS_REGION", "AWS_DEFAULT_REGION", "AWS_PAGER", "AWS_DEFAULT_OUTPUT"}
AWS_ENV_RE = re.compile(r"(?<![A-Za-z0-9_])(AWS_[A-Za-z0-9_]+)=(['\"]?)([^\s'\";&|()]*)")
SDK_RE = re.compile(r"boto3|botocore|aws-sdk")  # also matches @aws-sdk/...
IAC_TOOLS = {"terraform", "cdk"}  # checked for AWS_* overrides; J4 pins them via AWS_PROFILE
TF_MUTATING = {"apply", "destroy", "import", "state", "taint", "untaint", "refresh", "force-unlock", "login"}
CDK_PACKAGES = {"cdk", "aws-cdk"}  # npx [opts] cdk|aws-cdk[@version]
NPX_VALUE_OPTS = {"-p", "--package", "--cache", "--userconfig"}
SOURCE_CMDS = {"source", "."}
BRACE_RE = re.compile(r"\{([^{}]*,[^{}]*)\}")
INLINE_FLAGS = {"node": {"-e", "--eval", "-p", "--print"}, "bun": {"-e", "--eval", "-p", "--print"},
                "ruby": {"-e"}, "perl": {"-e", "-E"}}
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
VAR_RE = re.compile(r"^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?$")
DECLARERS = {"export", "readonly", "declare", "typeset", "local"}
PYTHON_RE = re.compile(r"^python[0-9.]*$")
REDIR_RE = re.compile(r"<<<|<<-|<<|<>|<&|>>|>&|>\||<|>")

KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "fi", "do", "done",
            "while", "until", "time", "function"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "mksh", "fish"}
# wrapper -> (options that take a value, positional args before the command)
WRAPPERS = {
    "env": ({"-u", "--unset", "-C", "--chdir", "-P"}, 0),
    "sudo": ({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T", "--user", "--group"}, 0),
    "doas": ({"-u", "-C"}, 0),
    "nohup": (set(), 0), "builtin": (set(), 0), "exec": ({"-a"}, 0),
    "noglob": (set(), 0), "time": (set(), 0), "busybox": (set(), 0),
    "nice": ({"-n", "--adjustment"}, 0), "ionice": ({"-c", "-n", "-p", "--class", "--classdata"}, 0),
    "timeout": ({"-s", "--signal", "-k", "--kill-after"}, 1),
    "gtimeout": ({"-s", "--signal", "-k", "--kill-after"}, 1),
    "stdbuf": ({"-i", "-o", "-e"}, 0), "caffeinate": ({"-t", "-w"}, 0),
    "unbuffer": (set(), 0), "chronic": (set(), 0),
    "command": (set(), 0),
    "watch": ({"-n", "--interval"}, 0),
    "xargs": ({"-I", "-n", "-P", "-L", "-s", "-d", "-E", "-a", "-R", "-S", "-J", "--arg-file",
               "--delimiter", "--max-args", "--max-procs", "--max-lines", "--replace", "--eof",
               "--max-chars", "--process-slot-var"}, 0),
    "parallel": ({"-j", "--jobs", "-S", "--sshlogin", "-a", "--arg-file", "-d", "--delimiter",
                  "-I", "--colsep", "-N", "-n", "-L", "-P", "--max-args", "--max-procs"}, 0),
}
ARGS_FROM_OUTSIDE = {"xargs", "parallel"}      # append arguments the hook cannot see
CRED_INJECTORS = {"aws-vault", "assume", "granted", "aws-sso-util"}

AWS_VALUE_OPTS = {"--profile", "--region", "--output", "--endpoint-url", "--query", "--ca-bundle",
                  "--cli-read-timeout", "--cli-connect-timeout", "--color", "--cli-binary-format"}
AWS_FLAG_OPTS = {"--no-verify-ssl", "--no-paginate", "--no-sign-request",
                 "--no-cli-pager", "--cli-auto-prompt", "--no-cli-auto-prompt"}

ALLOW_EXACT = {("s3", "ls"), ("configure", "list"), ("configure", "list-profiles"),
               ("sts", "get-caller-identity")}
ALLOW_PREFIXES = ("describe-", "list-", "get-")
ASK_OPS = {("athena", "start-query-execution"), ("logs", "start-query"),
           ("athena", "get-query-results"), ("logs", "get-query-results")}
DATA_OPS = {
    ("secretsmanager", "get-secret-value"), ("secretsmanager", "batch-get-secret-value"),
    ("kms", "decrypt"), ("s3api", "select-object-content"),
    ("dynamodb", "get-item"), ("dynamodb", "batch-get-item"), ("dynamodb", "query"),
    ("dynamodb", "scan"), ("dynamodb", "execute-statement"),
    ("glacier", "get-job-output"), ("ebs", "get-snapshot-block"),
    ("codecommit", "get-blob"), ("codecommit", "get-file"), ("codecommit", "get-folder"),
    ("logs", "get-log-events"), ("logs", "get-log-record"), ("logs", "filter-log-events"),
    ("logs", "tail"), ("logs", "start-live-tail"), ("sqs", "receive-message"),
    ("ec2", "get-console-output"), ("ec2", "get-console-screenshot"),
    ("appconfig", "get-configuration"), ("appconfigdata", "get-latest-configuration"),
    ("rds", "generate-db-auth-token"), ("lightsail", "get-instance-access-details"),
    ("cognito-idp", "list-users"), ("cognito-idp", "list-users-in-group"),
    ("cognito-idp", "describe-user-pool-client"), ("stepfunctions", "describe-execution"),
    ("stepfunctions", "get-execution-history"), ("ssm", "get-command-invocation"),
    ("appsync", "list-api-keys"),
}
DATA_SERVICES = {"iot-data", "kinesis-video-media", "kinesis-video-archived-media",
                 "mediastore-data", "sagemaker-runtime", "bedrock-runtime",
                 "bedrock-agent-runtime", "qldb-session"}
PASSWORD_OK = {"get-account-password-policy"}
HIDE_PASSWORD_OPS = {("glue", "get-connection"), ("glue", "get-connections")}  # data unless --hide-password
MUTATING_VERBS = {
    "create", "delete", "put", "update", "modify", "attach", "detach", "associate", "disassociate",
    "terminate", "stop", "start", "run", "reboot", "tag", "untag", "register", "deregister", "enable",
    "disable", "restore", "import", "copy", "authorize", "revoke", "replace", "reset", "set", "cancel",
    "send", "execute", "remove", "add", "upload", "accept", "reject", "purchase", "allocate", "release",
    "apply", "rotate", "change", "initiate", "complete", "batch", "admin", "request", "assign",
    "unassign", "promote", "failover", "purge", "schedule", "export", "retire", "generate", "test",
    "upgrade", "resume", "suspend", "move", "transfer", "merge", "archive", "flush", "rebuild", "resize",
    "restart", "switchover", "recover", "invoke", "publish", "deploy", "package", "subscribe",
    "unsubscribe", "transact", "leave", "invite", "write", "continue", "signal", "monitor", "sign",
    "encrypt", "cp", "mv", "rm", "sync", "mb", "rb", "presign", "website",
}


class ParseError(Exception):
    pass


# ---------------------------------------------------------------- tokenizer

def _find_backtick(s, i):
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == "`":
            return i
        i += 1
    raise ParseError("unterminated backtick")


def _skip_dquote(s, i):
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
        elif c == '"':
            return i + 1
        elif s.startswith("$(", i):
            i = _match_paren(s, i + 2) + 1
        elif c == "`":
            i = _find_backtick(s, i + 1) + 1
        else:
            i += 1
    raise ParseError("unterminated double quote")


def _match_paren(s, i):
    """Index of the ')' closing a '(' that ends just before s[i]."""
    depth = 1
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                raise ParseError("unterminated single quote")
            i = j + 1
            continue
        if c == '"':
            i = _skip_dquote(s, i + 1)
            continue
        if c == "`":
            i = _find_backtick(s, i + 1) + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ParseError("unbalanced parenthesis")


class _Splitter:
    """Quote-aware split of a shell string into simple commands (lists of words).

    Commands inside $(...), backticks and <(...) are added as separate commands.
    Heredoc bodies and redirection targets are dropped.
    """

    def __init__(self, s, depth):
        if depth > MAX_DEPTH:
            raise ParseError("nesting too deep")
        self.s, self.n, self.i, self.depth = s, len(s), 0, depth
        self.cmds, self.words, self.cur = [], [], []
        self.in_word = False
        self.redirect_next = False
        self.heredoc_next = None
        self.heredocs = []

    def run(self):
        s = self.s
        while self.i < self.n:
            c = s[self.i]
            nxt = s[self.i + 1] if self.i + 1 < self.n else ""
            if c in " \t":
                self._end_word()
                self.i += 1
            elif c == "\n":
                self._end_cmd()
                self.i += 1
                self._skip_heredocs()
            elif c == "#" and not self.in_word:
                j = s.find("\n", self.i)
                self.i = self.n if j < 0 else j
            elif c == "\\":
                if nxt == "\n":
                    self.i += 2
                elif nxt:
                    self._add(nxt)
                    self.i += 2
                else:
                    self.i += 1
            elif c == "'":
                j = s.find("'", self.i + 1)
                if j < 0:
                    raise ParseError("unterminated single quote")
                self._add(s[self.i + 1:j])
                self.i = j + 1
            elif c == '"':
                self._dquote()
            elif c == "`":
                j = _find_backtick(s, self.i + 1)
                self._nested(s[self.i + 1:j].replace("\\`", "`"))
                self.i = j + 1
            elif c == "$":
                self._dollar(nxt)
            elif c in "<>" and nxt == "(" and not self.in_word:
                j = _match_paren(s, self.i + 2)
                self._nested(s[self.i + 2:j])
                self.i = j + 1
            elif c in "<>":
                self._redirect()
            elif c == "&" and nxt == ">":
                self._end_word()
                self.i += 3 if s.startswith("&>>", self.i) else 2
                self.redirect_next = True
            elif c in "&|":
                self._end_cmd()
                self.i += 2 if nxt in "&|" else 1
            elif c == ";":
                self._end_cmd()
                self.i += 2 if nxt in ";&" else 1
            elif c in "()":
                self._end_cmd()
                self.i += 1
            else:
                self._add(c)
                self.i += 1
        self._end_cmd()
        return self.cmds

    def _add(self, text):
        self.cur.append(text)
        self.in_word = True

    def _end_word(self):
        if self.in_word:
            w = "".join(self.cur)
            if self.redirect_next:
                self.redirect_next = False
            elif self.heredoc_next is not None:
                self.heredocs.append((w, self.heredoc_next))
                self.heredoc_next = None
            else:
                self.words.append(w)
        self.cur, self.in_word = [], False

    def _end_cmd(self):
        self._end_word()
        if self.words:
            self.cmds.append(self.words)
        self.words = []

    def _skip_heredocs(self):
        for delim, strip_tabs in self.heredocs:
            while self.i < self.n:
                j = self.s.find("\n", self.i)
                j = self.n if j < 0 else j
                line = self.s[self.i:j]
                self.i = j + 1
                if (line.lstrip("\t") if strip_tabs else line) == delim:
                    break
        self.heredocs = []

    def _nested(self, inner):
        self.cmds.extend(_Splitter(inner, self.depth + 1).run())
        self._add(SUBST)

    def _dquote(self):
        s, i = self.s, self.i + 1
        self.in_word = True
        while i < self.n:
            c = s[i]
            if c == "\\" and i + 1 < self.n:
                if s[i + 1] in '$`"\\':
                    self._add(s[i + 1])
                elif s[i + 1] != "\n":
                    self._add(c + s[i + 1])
                i += 2
            elif c == '"':
                self.i = i + 1
                return
            elif s.startswith("$((", i):
                j = _match_paren(s, i + 2)
                self._add("$((...))")
                i = j + 1
            elif s.startswith("$(", i):
                j = _match_paren(s, i + 2)
                self._nested(s[i + 2:j])
                i = j + 1
            elif c == "`":
                j = _find_backtick(s, i + 1)
                self._nested(s[i + 1:j].replace("\\`", "`"))
                i = j + 1
            else:
                self._add(c)
                i += 1
        raise ParseError("unterminated double quote")

    def _dollar(self, nxt):
        s = self.s
        if self.s.startswith("$((", self.i):
            self.i = _match_paren(s, self.i + 2) + 1
            self._add("$((...))")
        elif nxt == "(":
            j = _match_paren(s, self.i + 2)
            self._nested(s[self.i + 2:j])
            self.i = j + 1
        elif nxt == "'":  # ANSI-C quoting: decode escapes so $'\x61ws' is seen as aws
            j, buf = self.i + 2, []
            while j < self.n and s[j] != "'":
                step = 2 if s[j] == "\\" else 1
                buf.append(s[j:j + step])
                j += step
            if j >= self.n:
                raise ParseError("unterminated $'...'")
            try:
                text = "".join(buf).encode("latin-1", "backslashreplace").decode("unicode_escape")
            except UnicodeDecodeError as exc:
                raise ParseError("bad escape in $'...'") from exc
            self._add(text)
            self.i = j + 1
        elif nxt == "{":
            j = s.find("}", self.i + 2)
            if j < 0:
                raise ParseError("unterminated ${")
            self._add(s[self.i:j + 1])
            self.i = j + 1
        else:
            self._add("$")
            self.i += 1

    def _redirect(self):
        if self.in_word and "".join(self.cur).isdigit():
            self.cur, self.in_word = [], False  # fd number such as 2>
        else:
            self._end_word()
        op = REDIR_RE.match(self.s, self.i).group()
        self.i += len(op)
        if op in ("<<", "<<-"):
            self.heredoc_next = op == "<<-"
        else:
            self.redirect_next = True


def split_commands(s, depth=0):
    return _Splitter(s, depth).run()


# ---------------------------------------------------------------- classifier

def _normalize(text):
    return re.sub(r"['\"\\]", "", text).lower()


def _unwrap(argv, spec):
    opts, npos = spec
    j = 1
    while j < len(argv):
        w = argv[j]
        if w == "--":
            j += 1
            break
        if ASSIGN_RE.match(w):
            j += 1
        elif w.startswith("-") and len(w) > 1:
            j += 2 if w in opts else 1
        else:
            break
    return argv[j + npos:]


def _remember(word, ctx):
    """Record NAME=value so a later $NAME command word can be resolved."""
    if ASSIGN_RE.match(word):
        key, value = word.split("=", 1)
        ctx["vars"][key] = value


def classify_command(words, ctx, depth):
    i = 0
    while i < len(words) and (words[i] in KEYWORDS or ASSIGN_RE.match(words[i])):
        i += 1
    if i == len(words) or words[i] in DECLARERS:  # prefix assignments do not affect $NAME expansion
        for w in words:
            _remember(w, ctx)
        if i < len(words) and words[i] == "export":
            ctx["exported"].update(w.split("=", 1) for w in words[i + 1:] if ASSIGN_RE.match(w))
    if i == len(words):
        return []
    return _with_env(ctx, words[:i], lambda: classify_argv(words[i:], ctx, depth))


def _with_env(ctx, words, run):
    """Run a classification with NAME=value words added to the command's environment."""
    saved = ctx["env"]
    ctx["env"] = {**saved, **dict(w.split("=", 1) for w in words if ASSIGN_RE.match(w))}
    try:
        return run()
    finally:
        ctx["env"] = saved


def classify_terraform(argv, ctx):
    """plan/init need AWS credentials: without AWS_PROFILE=<ro-profile> they use the shell's."""
    words = [w for w in argv[1:] if not w.startswith("-")]
    flags = [w for w in argv[1:] if w.startswith("-")]
    sub, arg = (words + ["", ""])[:2]
    if sub in TF_MUTATING or (sub == "workspace" and arg in ("new", "delete")) \
            or (sub == "plan" and any(f.startswith("-out") for f in flags)) \
            or (sub == "init" and "-migrate-state" in flags):
        return [("deny", f"terraform {sub} changes state or writes a saved plan. A denied command is "
                         "final: give it to the user as text under '# MUTATING: run yourself'.")]
    if sub not in ("plan", "init"):
        return [("defer", "terraform: static rules decide")]
    profile = ctx["env"].get("AWS_PROFILE", ctx["exported"].get("AWS_PROFILE", ""))
    if PROFILE_RE.match(profile):
        return [("defer", f"terraform {sub} pinned to {profile}")]
    return [("ask", f"terraform {sub} without AWS_PROFILE={PROFILE_HINT} uses the shell's credentials; "
                    "approve only if intended.")]


def classify_dynamic(argv, ctx, depth, via):
    """Command word is a variable or substitution: resolve a same-command
    assignment when possible, otherwise ask the user."""
    name = argv[0]
    var = VAR_RE.match(name)
    if var and var.group(1) in ctx["vars"] and ctx["vars"][var.group(1)] != name:
        return classify_argv([ctx["vars"][var.group(1)]] + argv[1:], ctx, depth + 1, via)
    out = [("ask", f"command word {name!r} is computed at run time; the hook cannot see "
                   "what runs. Confirm it, or write the command literally.")]
    return out + classify_shell(argv, ctx, depth)  # may be a shell: check -c scripts and stdin


def classify_argv(argv, ctx, depth, via=None):
    if not argv:
        return []
    name = argv[0]
    base = os.path.basename(name).lower()
    if base == "aws":
        if via in ARGS_FROM_OUTSIDE:
            return [("deny", f"aws via {via}: arguments come from outside the command text. "
                             f"Run aws directly with --profile {PROFILE_HINT}.")]
        return [classify_aws(argv)]
    if "$" in name or "`" in name:
        if depth > MAX_DEPTH:
            return [("deny", "variable command word nests too deep; fail closed.")]
        return classify_dynamic(argv, ctx, depth, via)
    if BRACE_RE.search(name):
        if any(os.path.basename(w).lower() == "aws" for w in _brace_expand(name)):
            return [("deny", f"brace expansion {name!r} can resolve to aws. Write the aws call literally.")]
        return [("ask", f"command word {name!r} uses brace expansion; the hook cannot see what runs. "
                        "Confirm it, or write the command literally.")]
    if any(ch in name for ch in "*?["):
        if fnmatch.fnmatchcase("aws", base):
            return [("deny", f"glob {name!r} can resolve to aws. Write the aws call literally.")]
        return []
    if PYTHON_RE.match(base) or base in INLINE_FLAGS or base == "deno":
        return classify_interpreter(base, argv, ctx)
    if base in SOURCE_CMDS:
        return classify_source(argv, ctx)
    if base == "npx":
        return classify_npx(argv, ctx, depth)
    if base == "curl":
        if any(w.startswith("--aws-sigv4") for w in argv[1:]):
            return [("deny", "curl --aws-sigv4 calls AWS APIs outside the aws CLI rules. Use the aws CLI.")]
        return []
    if base == "terraform":
        return classify_terraform(argv, ctx)
    if base in IAC_TOOLS:
        return [("defer", f"{base}: static rules decide; AWS_* overrides checked")]
    if base in SHELLS:
        return classify_shell(argv, ctx, depth)
    if base == "eval":
        return nested(" ".join(argv[1:]), ctx, depth)
    if base in CRED_INJECTORS:
        if any("aws" in w.lower() for w in argv[1:]):
            return [("deny", f"aws under {base}: injected credentials override the read-only "
                             "profile. Run aws directly.")]
        return []
    if base == "find":
        out = []
        for k, w in enumerate(argv):
            if w in ("-exec", "-execdir", "-ok", "-okdir"):
                end = k + 1
                while end < len(argv) and argv[end] not in (";", "+"):
                    end += 1
                out += classify_argv(argv[k + 1:end], ctx, depth)
        return out
    if base == "command" and any(w in ("-v", "-V") for w in argv[1:2]):
        return []
    if base == "env":
        for k, w in enumerate(argv[1:], 1):
            if w in ("-S", "--split-string") and k + 1 < len(argv):
                return nested(argv[k + 1], ctx, depth)
            if w.startswith("--split-string="):
                return nested(w.split("=", 1)[1], ctx, depth)
            if w.startswith("-S") and len(w) > 2:
                return nested(w[2:], ctx, depth)
    if base in WRAPPERS:
        rest = _unwrap(argv, WRAPPERS[base])
        if base == "watch":
            return nested(" ".join(rest), ctx, depth)
        run = lambda: classify_argv(rest, ctx, depth, via=base if base in ARGS_FROM_OUTSIDE else via)  # noqa: E731
        return _with_env(ctx, argv[1:len(argv) - len(rest)], run) if base == "env" else run()
    return []


def classify_interpreter(base, argv, ctx):
    """python*/node/bun/ruby/perl/deno running inline or stdin code that uses an AWS SDK -> deny.
    Script files are not read (residual risk, see SETUP)."""
    python = PYTHON_RE.match(base)
    if python and "-m" in argv and argv.index("-m") + 1 < len(argv) \
            and argv[argv.index("-m") + 1] == "awscli":
        return [("deny", "python -m awscli bypasses the aws CLI rules. Use the aws CLI directly.")]
    inline_flags = INLINE_FLAGS.get(base, set())
    value_opts = {"-W", "-X", "-Q"} if python else {"-r", "--require", "--import", "-I"}
    code, script, k = [], None, 1
    if base == "deno":
        code = argv[2:3] if argv[1:2] == ["eval"] else []
        script = None if code else (argv[1] if len(argv) > 1 else None)
        k = len(argv)
    while k < len(argv):
        w = argv[k]
        if w in inline_flags or (python and re.match(r"^-[A-Za-z]*c$", w)):
            code.append(argv[k + 1] if k + 1 < len(argv) else "")
            break
        if w in value_opts:
            k += 2
            continue
        if w == "-" or not w.startswith("-"):
            script = w
            break
        k += 1
    stdin = not code and (script == "-" or len(argv) == 1)
    if (code and any(SDK_RE.search(w) for w in argv[1:])) or (stdin and ctx["sdk"]):
        return [("deny", f"{base} inline code uses an AWS SDK (boto3/botocore/aws-sdk), which bypasses "
                         "the aws CLI rules. Use the aws CLI with the read-only profile.")]
    return []


def classify_source(argv, ctx):
    """source/. run a file in this shell: stdin-like targets are checked like `sh` reading stdin."""
    target = argv[1] if len(argv) > 1 else "-"
    if (target in ("-", SUBST) or target.startswith("/dev/stdin") or target.startswith("/dev/fd/")) \
            and ctx["mentions"]:
        return [("deny", f"{argv[0]} runs commands from stdin or a substitution in a command that "
                         "mentions aws. Run aws directly.")]
    return []


def classify_npx(argv, ctx, depth):
    """npx -c runs a shell string; npx cdk|aws-cdk joins the cdk branch (AWS_* checks)."""
    k = 1
    while k < len(argv) and argv[k].startswith("-"):
        w = argv[k]
        if w in ("-c", "--call") and k + 1 < len(argv):
            return nested(argv[k + 1], ctx, depth)
        k += 2 if w in NPX_VALUE_OPTS else 1
    pkg = argv[k].rsplit("@", 1)[0] if k < len(argv) and not argv[k].startswith("@") else ""
    if pkg in CDK_PACKAGES:
        return [("defer", "npx cdk: static rules decide; AWS_* overrides checked")]
    return []


def _brace_expand(word, limit=64):
    m = BRACE_RE.search(word)
    if not m:
        return [word]
    out = []
    for alt in m.group(1).split(","):
        out += _brace_expand(word[:m.start()] + alt + word[m.end():], limit)
        if len(out) > limit:
            break
    return out


def classify_shell(argv, ctx, depth):
    j, has_c, stdin = 1, False, False
    while j < len(argv):
        w = argv[j]
        if w == "--":
            j += 1
            break
        if w in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
            j += 2
            continue
        if w == "--command":
            has_c = True
        elif w.startswith("-") and not w.startswith("--") and len(w) > 1:
            has_c = has_c or "c" in w[1:]
            stdin = stdin or "s" in w[1:]
        elif not (w.startswith("--") or w.startswith("+")):
            break
        j += 1
    rest = argv[j:]
    if has_c:
        return nested(rest[0], ctx, depth) if rest else []
    if (not rest or stdin) and ctx["mentions"]:
        return [("deny", "shell reads commands from stdin or a heredoc in a command that "
                         "mentions aws. Run aws directly.")]
    return []


def nested(text, ctx, depth):
    try:
        cmds = split_commands(text, depth + 1)
    except ParseError as exc:
        if "aws" in _normalize(text) or ctx["mentions"]:
            return [("deny", f"cannot parse nested command ({exc}); fail closed.")]
        return []
    out = []
    for words in cmds:
        out += classify_command(words, ctx, depth + 1)
    return out


def _profiles(args):
    found = []
    for k, w in enumerate(args):
        if w == "--profile":
            found.append(args[k + 1] if k + 1 < len(args) else "")
        elif w.startswith("--profile="):
            found.append(w.split("=", 1)[1])
    return found


def classify_op(svc, op, args):
    if svc == "configure":
        if op in ("list", "list-profiles"):
            return "defer", f"read: aws configure {op}"
        return "deny", f"aws configure {op} reads or writes credentials/config. The user runs it themselves."
    if (svc, op) in DATA_OPS or svc in DATA_SERVICES or op.startswith("get-object") \
            or op == "get-records" or op.startswith("get-statement-result") \
            or (svc == "ssm" and op.startswith("get-parameter")) or "--with-decryption" in args \
            or any(a.startswith("--include-value") for a in args) \
            or ((svc, op) in HIDE_PASSWORD_OPS and "--hide-password" not in args):
        return "deny", f"aws {svc} {op} reads data or secret content, not metadata. Forbidden."
    if "secret-value" in op or ("password" in op and op not in PASSWORD_OK) \
            or (op.startswith("get-") and "token" in op) or "credentials" in op \
            or op.startswith("assume-role"):
        return "deny", f"aws {svc} {op} returns secrets, tokens or credentials. Forbidden."
    if (svc, op) == ("sso", "login"):
        return "ask", "aws sso login opens a browser sign-in. The user signs in themselves; approve only if you started it."
    if (svc, op) in ASK_OPS:
        return "ask", f"aws {svc} {op} is a paid or data-exposing query. Confirm scope and cost with the user."
    if (svc, op) in ALLOW_EXACT or op.startswith(ALLOW_PREFIXES):
        return "defer", f"read: aws {svc} {op}"
    if op.split("-", 1)[0] in MUTATING_VERBS:
        return "deny", (f"aws {svc} {op} changes AWS state. A denied command is final: "
                        "give it to the user as text under '# MUTATING: run yourself'.")
    return "deny", (f"aws {svc} {op} is not in the read allowlist (describe-/list-/get- metadata only). "
                    "A denied command is final: give it to the user as text to run themselves.")


def classify_aws(argv):
    args = argv[1:]
    pos, j = [], 0
    while j < len(args) and len(pos) < 2:
        w = args[j]
        if w.startswith("--"):
            key = w.split("=", 1)[0]
            if key in AWS_VALUE_OPTS:
                j += 1 if "=" in w else 2
                continue
            if key in AWS_FLAG_OPTS:
                j += 1
                continue
            if w == "--version" and not pos:
                return "defer", "aws --version"
            return "deny", f"unrecognized aws option {w!r} before the operation; fail closed."
        if w.startswith("-") and w != "-":
            return "deny", f"unrecognized aws option {w!r} before the operation; fail closed."
        pos.append(w)
        j += 1
    if not pos:
        return "deny", "aws call without a service and operation."
    svc, op = pos[0].lower(), (pos[1].lower() if len(pos) > 1 else "")
    if "--debug" in args:
        return "deny", "aws --debug prints signed request headers, including the session token. Forbidden."
    if svc == "help" or op == "help":
        return "defer", "aws help"
    if not op:
        return "deny", f"aws {svc}: no operation given."
    if any(ch in svc + op for ch in "$`*?["):
        return "deny", "aws service or operation is dynamic. Write it literally."
    decision, reason = classify_op(svc, op, args)
    if decision == "deny":
        return decision, reason
    profiles = _profiles(args)
    if not profiles:
        return "deny", (f"aws {svc} {op}: add --profile {PROFILE_HINT}. "
                        "Every aws call must name a read-only profile.")
    if not all(PROFILE_RE.match(p) for p in profiles):
        return "deny", f"aws {svc} {op}: only --profile {PROFILE_HINT} is allowed."
    return decision, reason


def decide(command):
    """Return (decision, reason); decision is 'deny', 'ask' or 'defer'."""
    norm = _normalize(command)
    ctx = {"mentions": "aws" in norm, "vars": {}, "sdk": bool(SDK_RE.search(command)),
           "env": {}, "exported": {}}
    try:
        cmds = split_commands(command)
    except ParseError as exc:
        if ctx["mentions"]:
            return "deny", f"cannot parse a command that mentions aws ({exc}); fail closed. Simplify it."
        return "defer", "not parseable, no aws"
    findings = []
    for words in cmds:
        findings += classify_command(words, ctx, 0)
    if findings:
        bad_env = sorted({m.group(1) for m in AWS_ENV_RE.finditer(command)
                          if m.group(1) not in SAFE_AWS_ENV
                          and not (m.group(1) == "AWS_PROFILE" and PROFILE_RE.match(m.group(3)))})
        if bad_env:
            findings.append(("deny", f"AWS environment override {', '.join(bad_env)} is not allowed; "
                                     f"use --profile {PROFILE_HINT} for aws, or AWS_PROFILE=<ro-profile> for terraform/cdk."))
    denies = list(dict.fromkeys(r for d, r in findings if d == "deny"))
    if denies:
        return "deny", " | ".join(denies)
    asks = list(dict.fromkeys(r for d, r in findings if d == "ask"))
    if asks:
        return "ask", " | ".join(asks)
    return "defer", "no aws call, or allowed aws reads only"


# ---------------------------------------------------------------- hook I/O

def render(decision, reason):
    if decision not in ("deny", "ask"):
        return ""
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": f"aws-guard: {reason}",
    }})


def handle(raw):
    """Map raw hook stdin to stdout text. Empty output defers to normal rules."""
    try:
        data = json.loads(raw)
        if data.get("tool_name", "Bash") != "Bash":
            return ""
        command = (data.get("tool_input") or {}).get("command", "")
        if not isinstance(command, str):
            raise ValueError("tool_input.command is not a string")
    except (ValueError, AttributeError) as exc:
        if "aws" in _normalize(raw):
            return render("deny", f"unreadable hook input ({exc}); fail closed.")
        return ""
    try:
        return render(*decide(command))
    except Exception as exc:  # noqa: BLE001 - any internal failure fails closed for aws
        if "aws" in _normalize(command):
            return render("deny", f"internal error ({type(exc).__name__}); fail closed.")
        return ""


# ---------------------------------------------------------------- self-test

P = f"--profile {PROFILE}"
CASES = [
    # allowed reads -> defer
    ("defer", f"aws sts get-caller-identity {P}"),
    ("defer", f"aws ec2 describe-instances --region us-east-1 {P} --output json"),
    ("defer", f"aws {P} s3 ls"),
    ("defer", f"aws ce get-cost-and-usage --time-period Start=2026-09-01,End=2026-09-29 "
              f"--granularity MONTHLY --metrics UnblendedCost --profile={PROFILE}"),
    ("defer", f"aws pricing get-products --service-code AmazonEC2 --region us-east-1 {P} \\\n"
              f"  --filters Type=TERM_MATCH,Field=regionCode,Value=eu-west-1"),
    ("defer", f"aws service-quotas list-service-quotas --service-code ec2 {P} | jq '.Quotas[0]'"),
    ("defer", f'AWS_PAGER="" aws iam list-roles {P} 2>/dev/null'),
    ("defer", f"aws iam get-account-password-policy {P}"),
    ("defer", "aws --version"),
    ("defer", "aws s3 help"),
    # non-aws commands pass through
    ("defer", "cd infra && terraform validate"),
    ("defer", 'git commit -m "docs: explain aws s3 ls usage"'),
    ("defer", "grep -rn aws ./src | head"),
    ("defer", "command -v aws"),
    ("defer", "echo \"it's unbalanced"),
    # denied: profile, mutations, data, secrets, credentials
    ("deny", "aws s3 ls"),
    ("deny", "aws s3 ls --profile default"),
    ("deny", f"aws ec2 terminate-instances --instance-ids i-0abc {P}"),
    ("deny", f"aws ec2 start-instances --instance-ids i-0abc {P}"),
    ("deny", f"aws secretsmanager get-secret-value --secret-id app/db {P}"),
    ("deny", f"aws ssm get-parameter --name /app/key --with-decryption {P}"),
    ("deny", f"aws s3api get-object --bucket b --key k out.bin {P}"),
    ("deny", f"aws dynamodb scan --table-name t {P}"),
    ("deny", f"aws logs filter-log-events --log-group-name g {P}"),
    ("deny", f"aws s3 cp s3://b/k - {P}"),
    ("deny", f"aws configure export-credentials {P}"),
    ("deny", f"aws sts get-session-token {P}"),
    ("deny", f"aws ecr get-login-password {P}"),
    ("deny", f"aws --unknown-flag s3 ls {P}"),
    # bypass attempts
    ("deny", f"/opt/homebrew/bin/aws s3 rm s3://b/k --recursive {P}"),
    ("deny", f"sh -c 'aws s3 rb s3://b --force {P}'"),
    ("deny", 'bash -lc "aws ec2 describe-instances"'),
    ("deny", f"AWS_PROFILE=admin aws s3 ls {P}"),
    ("deny", f"env AWS_CONFIG_FILE=/tmp/c aws s3 ls {P}"),
    ("deny", f"export AWS_SHARED_CREDENTIALS_FILE=/tmp/x; aws s3 ls {P}"),
    ("deny", f"aws sts get-caller-identity {P} && aws iam create-user --user-name x {P}"),
    ("deny", f"echo ok; aws s3 mb s3://new {P}"),
    ("deny", f"ls | aws s3 rm s3://b/k {P}"),
    ("deny", f"false || aws lambda invoke --function-name f out.json {P}"),
    ("deny", f"echo $(aws secretsmanager get-secret-value --secret-id x {P})"),
    ("deny", f"echo \"`aws kms decrypt --ciphertext-blob fileb://x {P}`\""),
    ("deny", f"timeout 30 aws ec2 stop-instances --instance-ids i-1 {P}"),
    ("deny", "sudo -u root aws s3 ls"),
    ("deny", f"A=aws; $A s3 rm s3://b/k {P}"),
    ("deny", f"AWS s3 rm s3://b/k {P}"),
    ("deny", f'"a"ws s3 rm s3://b/k {P}'),
    ("deny", f"$'\\x61ws' s3 rm s3://b/k {P}"),
    ("deny", f'echo "aws s3 rm s3://b/k {P}" | bash'),
    ("deny", f"bash <<'EOF'\naws s3 rm s3://b/k {P}\nEOF"),
    ("deny", f"printf '%s\\n' s3://b/k | xargs aws s3 rm {P}"),
    ("deny", f"find . -name '*.json' -exec aws s3 cp {{}} s3://b/ {P} \\;"),
    ("deny", f'eval "aws iam delete-user --user-name x {P}"'),
    ("deny", f"python3 -m awscli s3 rm s3://b/k {P}"),
    ("deny", f"/usr/local/bin/a?s s3 ls {P}"),
    ("deny", f"aws-vault exec admin -- aws s3 ls {P}"),
    ("deny", f"aws s3 ls {P}'"),
    ("deny", f"env -S 'aws s3 rm s3://b/k {P}'"),
    ("deny", f"busybox sh -c 'aws s3 rm s3://b/k {P}'"),
    ("deny", "watch -n 5 aws ec2 describe-instances"),
    ("deny", f"aws s3 ls {P} --profile admin"),
    ("deny", f"if true; then aws iam delete-role --role-name r {P}; fi"),
    ("defer", "echo hi | xargs grep aws"),
    ("defer", "find ~ -name aws -type f"),
    # ask: paid or data-exposing queries
    ("ask", f"aws athena start-query-execution --query-string 'SELECT 1' --work-group primary {P}"),
    ("ask", f"aws logs start-query --log-group-name g --start-time 1 --end-time 2 "
            f"--query-string 'fields @message | limit 5' {P}"),
    ("ask", f"aws logs get-query-results --query-id q1 {P}"),
    ("ask", f"aws sts get-caller-identity {P} && aws athena start-query-execution --query-string x {P}"),
    ("deny", "aws athena start-query-execution --query-string 'SELECT 1'"),
    # (a) per-account read-only profiles
    ("defer", f"aws s3 ls --profile {PROFILE}-acme"),
    ("defer", f"aws ec2 describe-vpcs --profile={PROFILE}-client-prod.eu"),
    ("defer", f"aws sts get-caller-identity --profile {PROFILE}-acme && aws iam list-roles {P}"),
    ("deny", f"aws s3 ls --profile {PROFILE}-"),
    ("deny", f"aws s3 ls --profile {PROFILE}x"),
    ("deny", f"aws s3 ls --profile admin-{PROFILE}"),
    ("deny", f"aws s3 ls --profile {PROFILE}-$X"),
    ("deny", f"aws s3 ls --profile \"{PROFILE}-$(id -un)\""),
    ("deny", f"aws s3 ls --profile {PROFILE}-acme --profile admin"),
    ("deny", f"aws s3 rm s3://b/k --profile {PROFILE}-acme"),
    # (c) command word computed at run time -> ask (deny still wins)
    ("ask", f"$(printf '\\x61ws') s3 ls {P}"),
    ("ask", "$(printf '\\x61ws') s3 rm s3://b/k"),
    ("ask", "`printf aws` s3 rm s3://b/k"),
    ("ask", "$CMD s3 rm s3://b/k"),
    ("ask", "${TOOL} --version"),
    ("ask", "sudo $X ls"),
    ("ask", f'"$SHELL" -c \'aws ec2 describe-instances {P}\''),
    ("ask", '"$(git rev-parse --show-toplevel)/scripts/build.sh"'),
    ("deny", f'"$SHELL" -c \'aws s3 rm s3://b/k {P}\''),
    ("deny", f"$SHELL -lc 'aws iam delete-user --user-name x {P}'"),
    ("deny", f"export A=/usr/local/bin/aws; $A iam delete-user --user-name x {P}"),
    ("deny", "A=$B; B=$A; $A s3 ls"),
    ("deny", f'echo "aws s3 rm s3://b/k {P}" | $SHELL'),
    ("ask", "echo $HOME | $PAGER"),
    ("defer", f"A=aws; $A s3 ls {P}"),
    ("ask", f"A=aws $A s3 ls {P}"),
    ("defer", "echo $HOME"),
    ("defer", 'ls "$DIR"'),
    ("defer", f'cd "$PROJECT" && AWS_PROFILE={PROFILE} terraform plan -lock=false'),
    ("defer", "FOO=$(date +%F) make build"),
    ("defer", 'for f in $(ls); do echo "$f"; done'),
    ("defer", '[ -n "$X" ] && echo "${X}"'),
    ("defer", 'git log --format="%H $USER"'),
    ("defer", 'python3 "$HOME/.claude/hooks/aws-guard.py" --selftest'),
    # J4: terraform/cdk pinned with AWS_PROFILE=<ro-profile>
    ("defer", f"AWS_PROFILE={PROFILE} terraform plan -lock=false"),
    ("defer", f"cd infra && AWS_PROFILE={PROFILE}-acme terraform -chdir=env/prod plan -lock=false"),
    ("defer", f"AWS_PROFILE={PROFILE} npx cdk diff"),
    ("defer", f"AWS_PROFILE={PROFILE} terraform plan -lock=false && aws sts get-caller-identity {P}"),
    ("deny", "AWS_PROFILE=admin terraform plan -lock=false"),
    ("deny", "AWS_ACCESS_KEY_ID=AKIAEXAMPLE terraform plan"),
    ("deny", f"AWS_PROFILE={PROFILE}x terraform plan"),
    ("deny", "export AWS_PROFILE=admin; terraform plan -lock=false"),
    # terraform plan/init without AWS_PROFILE=<ro-profile> -> ask; no-credential subcommands defer
    ("ask", "terraform plan -lock=false"),
    ("ask", "terraform -chdir=x plan -lock=false"),
    ("ask", "cd infra && terraform init"),
    ("ask", "timeout 600 terraform plan -lock=false"),
    ("ask", "AWS_REGION=us-east-1 terraform plan -lock=false"),
    ("ask", "AWS_PROFILE=aws-expert-ro; terraform plan -lock=false"),
    ("defer", f"AWS_PROFILE={PROFILE} terraform -chdir=x plan -lock=false"),
    ("defer", f"AWS_PROFILE={PROFILE}-acme terraform init"),
    ("defer", f"env AWS_PROFILE={PROFILE} terraform plan -lock=false"),
    ("defer", f"AWS_PROFILE={PROFILE} timeout 600 terraform plan -lock=false"),
    ("defer", f"export AWS_PROFILE={PROFILE} && terraform plan -lock=false"),
    ("defer", f"AWS_PROFILE={PROFILE} sh -c 'terraform plan -lock=false'"),
    ("defer", "terraform validate"),
    ("defer", "terraform fmt -recursive"),
    ("defer", "terraform -chdir=x validate"),
    ("defer", "terraform version"),
    ("deny", "env AWS_PROFILE=admin terraform plan -lock=false"),
    # J2: inline AWS SDK code and SigV4 curl
    ("deny", "python3 -c 'import boto3; boto3.client(\"s3\").get_object(Bucket=\"b\", Key=\"k\")'"),
    ("deny", "python -Bc 'from botocore.session import Session'"),
    ("deny", "python3 -W ignore -c 'import boto3'"),
    ("deny", "node -e \"const {S3Client} = require('@aws-sdk/client-s3')\""),
    ("deny", "node --eval \"require('aws-sdk')\""),
    ("deny", "python3 - <<'EOF'\nimport boto3\nprint(boto3.client('sts'))\nEOF"),
    ("deny", "echo 'import boto3' | python3"),
    ("deny", "curl --aws-sigv4 'aws:amz:us-east-1:s3' https://b.s3.amazonaws.com/k"),
    ("deny", "curl -s --aws-sigv4=aws:amz:us-east-1:sts https://sts.amazonaws.com"),
    ("defer", "python3 -c 'print(1)'"),
    ("defer", "node -e 'console.log(1)'"),
    ("defer", "python3 scripts/report.py --bucket boto3-docs"),
    ("defer", "pip install boto3 && python3 --version"),
    ("defer", "python3 -m pip install boto3"),
    ("defer", "grep -rn boto3 requirements.txt"),
    ("defer", "curl -s https://aws.amazon.com/pricing/"),
    # J3: secret values on metadata calls
    ("deny", f"aws apigateway get-api-keys --include-values {P}"),
    ("deny", f"aws apigateway get-api-key --api-key k1 --include-value {P}"),
    ("defer", f"aws apigateway get-api-keys {P}"),
    # validation B7, B9-B13 (H1 data-returning reads, --debug)
    ("deny", f"aws sts get-caller-identity {P} --debug"),
    ("deny", f"aws --debug sts get-caller-identity {P}"),
    ("deny", f"aws cognito-idp list-users --user-pool-id X {P}"),
    ("deny", f"aws cognito-idp list-users-in-group --user-pool-id X --group-name g {P}"),
    ("deny", f"aws stepfunctions describe-execution --execution-arn arn:x {P}"),
    ("deny", f"aws stepfunctions get-execution-history --execution-arn arn:x {P}"),
    ("deny", f"aws glue get-connection --name db {P}"),
    ("deny", f"aws glue get-connections {P}"),
    ("deny", f"aws ssm get-command-invocation --command-id c --instance-id i-1 {P}"),
    ("deny", f"aws cognito-idp describe-user-pool-client --user-pool-id X --client-id Y {P}"),
    ("deny", f"aws appsync list-api-keys --api-id a {P}"),
    ("defer", f"aws glue get-connection --name db --hide-password {P}"),
    ("defer", f"aws iam list-users {P}"),
    ("defer", f"aws cognito-idp list-user-pools --max-results 10 {P}"),
    ("defer", f"aws stepfunctions describe-state-machine --state-machine-arn arn:x {P}"),
    ("defer", f"aws stepfunctions list-executions --state-machine-arn arn:x {P}"),
    # validation B1-B6, B8 (shell forms, pinned terraform mutations, npx cdk, other interpreters)
    ("deny", f"bash -c '{{aws,}} s3 rm s3://b/k --recursive {P}'"),
    ("deny", f'source <(echo "aws s3 rm s3://b/k {P}")'),
    ("deny", f'. /dev/stdin <<< "aws s3 rm s3://b/k {P}"'),
    ("deny", f"AWS_PROFILE={PROFILE} terraform apply -auto-approve"),
    ("deny", f"AWS_PROFILE={PROFILE} terraform plan -lock=false -out=tfplan"),
    ("deny", "AWS_PROFILE=admin npx cdk diff"),
    ("deny", "ruby -e \"require 'aws-sdk-s3'; Aws::S3::Client.new.get_object(bucket: 'b', key: 'k')\""),
    ("deny", f"AWS_PROFILE={PROFILE} terraform -chdir=infra destroy"),
    ("deny", f"AWS_PROFILE={PROFILE} terraform state rm aws_s3_bucket.b"),
    ("deny", f"AWS_PROFILE={PROFILE} terraform workspace new tmp"),
    ("deny", f"AWS_PROFILE={PROFILE} terraform plan -lock=false -out tfplan"),
    ("deny", f"AWS_PROFILE={PROFILE} terraform init -migrate-state"),
    ("deny", "terraform import aws_s3_bucket.b b"),
    ("deny", "AWS_PROFILE=admin npx --yes aws-cdk@2 diff"),
    ("deny", f"npx -c 'aws s3 rm s3://b/k {P}'"),
    ("deny", "perl -e 'use Paws; use aws-sdk'"),
    ("deny", "bun -e \"import {S3Client} from '@aws-sdk/client-s3'\""),
    ("deny", "deno eval \"import {S3Client} from 'npm:@aws-sdk/client-s3'\""),
    ("deny", f"/usr/local/bin/a{{w,x}}s s3 ls {P}"),
    ("ask", "{ls,} -la"),
    ("defer", f"AWS_PROFILE={PROFILE} terraform workspace list"),
    ("defer", f"AWS_PROFILE={PROFILE} npx --yes aws-cdk@2 diff"),
    ("defer", "npx cdk synth"),
    ("defer", "npx eslint ."),
    ("defer", "source ~/.zshrc"),
    ("defer", ". ./venv/bin/activate"),
    ("defer", "{ echo hi; echo there; }"),
    ("defer", "ruby -e 'puts 1'"),
    ("defer", "perl -e 'print 1'"),
    ("defer", "deno eval 'console.log(1)'"),
    ("defer", "bun -e 'console.log(1)'"),
    ("defer", "echo {a,b}.txt"),
    # sso login: ask with its own reason
    ("ask", f"aws sso login {P}"),
]

IO_CASES = [
    ('{"tool_name":"Bash","tool_input":{"command":"aws s3 ls"}}', "deny"),
    ('{"tool_name":"Bash","tool_input":{"command":"ls -la"}}', ""),
    ('{"tool_name":"Read","tool_input":{"file_path":"/tmp/aws"}}', ""),
    ('not json aws s3 rm', "deny"),
    ('{"tool_name":"Bash","tool_input":{"command":"aws athena start-query-execution '
     '--query-string x --profile aws-expert-ro"}}', "ask"),
    ('{"tool_name":"Bash","tool_input":{"command":"$CMD s3 ls"}}', "ask"),
    ('{"tool_name":"Bash","tool_input":{"command":"aws s3 ls --profile aws-expert-ro-acme"}}', ""),
]


def selftest():
    failures = 0
    for expected, cmd in CASES:
        got, reason = decide(cmd)
        if got != expected:
            failures += 1
            print(f"FAIL expected={expected} got={got} cmd={cmd!r}\n     reason={reason}")
    for raw, expected in IO_CASES:
        out = handle(raw)
        got = json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else ""
        if got != expected:
            failures += 1
            print(f"FAIL io expected={expected!r} got={got!r} stdin={raw!r}")
    total = len(CASES) + len(IO_CASES)
    print(f"aws-guard selftest: {total - failures}/{total} passed, {failures} failed")
    return 1 if failures else 0


def main():
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    out = handle(sys.stdin.read())
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
