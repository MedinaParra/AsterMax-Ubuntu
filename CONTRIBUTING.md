# Contributing to AsterMax

AsterMax welcomes contributions that preserve engineering quality and legal provenance.

## Contribution rules

Every contribution must:

1. be work you have the right to submit;
2. comply with `IP_POLICY.md`;
3. identify any copied or adapted open-source material and its license;
4. avoid proprietary source code, extracted implementation details, protected UI assets, screenshots, logos, manuals, and confidential information;
5. preserve upstream copyright and license notices;
6. add or update tests/validation evidence appropriate to the engineering change;
7. update `THIRD_PARTY_NOTICES.md` when introducing a distributed dependency or asset.

## Functional reference is allowed; copying is not

A contribution may implement a familiar CAD/CAE workflow based on engineering experience or lawfully observed behavior. Describe the requirement in functional terms and build an independent implementation. Do not submit a pixel-for-pixel recreation of another vendor's UI or code obtained through decompilation/disassembly.

## Developer Certificate of Origin sign-off

Commits intended for merge should include a `Signed-off-by:` line created with `git commit -s`. By signing off, the contributor certifies that they created the contribution or otherwise have the right to submit it under the project's license and understand that the contribution and sign-off are maintained in the public project history.

## Employer/client rights

If your employment agreement, consulting agreement, customer contract, or other obligation may give another party rights in your work, obtain the necessary permission before contributing. Do not rely on AsterMax maintainers to resolve those obligations after submission.

## Review checklist

Reviewers should reject or quarantine a change if its provenance is unclear. For a new dependency or substantial externally inspired feature, the PR should state:

- source of the functional requirement;
- implementation provenance;
- third-party components/assets introduced;
- applicable licenses;
- validation method;
- whether a trademark, patent, file-format, or redistribution review is needed.
