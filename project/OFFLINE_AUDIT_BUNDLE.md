# Offline audit bundles

This repository can publish a complete, revision-pinned audit bundle for agents whose execution sandbox cannot reach GitHub or whose GitHub connector cannot enumerate recursive trees.

## Request a bundle

Add this exact command as a comment on any issue in the repository:

```text
/audit-bundle
```

The command is accepted only from an owner, member, or collaborator. The workflow checks out the repository's current default branch with full history and runs on both the configured Blacksmith pool and a GitHub-hosted Ubuntu runner. Each runner that succeeds posts a receipt comment containing the exact commit, tree, tracked-file count, and numeric artifact ID.

## Consume a bundle

Download the artifact using the numeric artifact ID in the receipt. Verify `SHA256SUMS`, then clone the Git bundle without network access:

```bash
git clone repository-<commit>.bundle audit-checkout
git -C audit-checkout rev-parse HEAD
git -C audit-checkout status --short
```

The artifact contains:

- `repository-<commit>.bundle`: authoritative complete Git history reachable from the audited commit and an offline-clone source.
- `source-<commit>.tar.gz`: deterministic snapshot of every tracked path in the clean checkout.
- `tracked-files.nul`: byte-sorted, NUL-delimited tracked-file population suitable for mechanical Stage A filtering.
- `tree.nul`: raw `git ls-tree -r -z --full-tree HEAD` output.
- `status.nul`: clean-checkout receipt. It is empty for a valid bundle.
- `manifest.json`: repository, commit, tree, timestamps, counts, digests, and usage notes.
- `SHA256SUMS`: integrity hashes for every payload file.

The generator refuses to publish when the checkout is dirty, the index differs from the commit tree, a path is unsafe, an unsupported tracked file type is encountered, the source archive omits or adds a tracked path, the Git bundle cannot be verified, or an offline clone does not resolve to the expected commit.

## Scope and limitations

This removes dependence on recursive-tree support in a connector and on outbound GitHub access from the consuming sandbox. Artifact production still requires at least one configured Actions runner to start. The dual-runner workflow provides two independent scheduling paths, but repository code cannot repair an account-level or platform-wide runner outage.
