# git_signing

Configures **SSH-based git commit signing** for one or more users on a host, so humans
and headless coding agents alike produce commits that satisfy GitHub's
*required signed commits* branch protection and show as **Verified**.

Why SSH signing: keys are plain files (no gpg-agent, no passphrase prompts for an agent
to wedge on), each host generates its own key, and a host is decommissioned by deleting
one key from the GitHub account.

For each user in `git_signing_users` the role:

1. Sets the git identity (`user.name` / `user.email`) — the email must be one GitHub
   associates with the account, so all users (including agent service accounts) commit
   as the same human identity.
2. Generates a dedicated, passphrase-less ed25519 key at
   `~/.ssh/github-commit-signing` if absent (never overwrites; private key never leaves
   the host).
3. Enables `gpg.format=ssh`, `user.signingkey`, `commit.gpgsign`, `tag.gpgsign` — every
   `git commit`/`git tag` signs transparently, nothing agent-specific to remember.
4. Installs `~/.config/git/allowed_signers`, built from the SSH signing keys registered
   on the GitHub account, so `git log --show-signature` verifies commits made by any
   host/user in the fleet.
5. Checks the local public key against the account's registered keys and prints the
   exact `gh api` command when it is missing (see below).

## The one manual step: key registration

GitHub key registration needs a token with the `admin:ssh_signing_key` scope, so it
stays a deliberate one-time action per key. The role reports any unregistered key with
a ready-to-run command:

```bash
gh auth refresh -h github.com -s admin:ssh_signing_key   # once per control machine
gh api /user/ssh_signing_keys -f title="<host>-<user>" -f key="$(cat ~/.ssh/github-commit-signing.pub)"
```

Set `git_signing_fail_on_unregistered: true` to make an unregistered key fail the run
instead of warning.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `git_signing_name` | `Jonathan Freed` | `user.name` for every configured user |
| `git_signing_email` | `53282525+jfreed-dev@users.noreply.github.com` | `user.email`; must be associated with the GitHub account |
| `git_signing_github_user` | `jfreed-dev` | Account whose registered keys feed `allowed_signers` and the registration check |
| `git_signing_users` | `[ansible_user]` | Users to configure; names or `{name, home}` dicts (home defaults to `/home/<name>`) |
| `git_signing_key_name` | `github-commit-signing` | Key basename under each user's `~/.ssh` |
| `git_signing_allowed_signers` | `true` | Install the fleet `allowed_signers` file |
| `git_signing_fail_on_unregistered` | `false` | Fail instead of warn on unregistered keys |

Configuring users other than the connection user (agent service accounts) uses
`become_user`, so the play needs privilege escalation rights on the target.

## Usage

Via `playbooks/git-signing.yml` against the NetBox inventory:

```bash
# One host, just its login user
ansible-playbook playbooks/git-signing.yml --limit mesh

# A host with an agent service account
ansible-playbook playbooks/git-signing.yml --limit mesh -e 'git_signing_users=["aria","hermes"]'
```

## Verify

```bash
d=$(mktemp -d); git -C "$d" init -q
git -C "$d" commit --allow-empty -m "signing smoke test"
git -C "$d" log -1 --format='%G?'   # G = good signature
rm -rf "$d"
```

Then push a scratch branch and confirm the commit shows **Verified** on GitHub.
