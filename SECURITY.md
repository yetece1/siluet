# Security

## What Silüet protects

| Threat | Protection |
|---|---|
| Someone gets an anonymized output file | Phone numbers, national IDs, surnames and other identifiers are replaced with values derived from a secret per-project key (HMAC-SHA256). Without the key, outputs cannot be mapped back by recomputation. Generated national IDs always fail the checksum. |
| Someone gets the project folder | The project file (key, mappings, source paths, group names) is encrypted with the user's password using scrypt (n = 2¹⁷, r = 8, p = 1) and AES-256-GCM. The format header is authenticated, so tampering with it fails decryption. |
| Tampered or crafted project file | Decryption fails closed. KDF parameters are bounded (scrypt memory ≤ 256 MiB, p ≤ 4), so a crafted header cannot exhaust memory. |
| Data leaking through side channels | Cell comments, document properties and hyperlink targets are removed from outputs. Error messages, reports and logs never include cell values; long digit runs in crash logs are masked. |
| Plain-text key left behind by a migration from v1 | Silüet detects the leftover backup on every open and offers to delete it. |
| Two windows writing one project | An OS file lock (flock / msvcrt) allows one open instance; it is released automatically when a process dies. |

## What it does not protect

- **First names and base station (BAZ) names are kept on purpose,** because analysis depends on them. Combined with outside knowledge, they can narrow down who someone is.
- **Pseudonymization is not anonymization in the legal sense.** Relationships, timing and locations are preserved by design. Decide case by case whether outputs may be shared.
- **A weak or reused password** weakens project-file protection. The minimum length is 10 characters; longer is better.
- **Secure deletion is best effort.** On SSDs, USB flash and copy-on-write file systems, overwritten blocks may survive physically.
- **A compromised computer** (malware, keylogger) is out of scope.

## Reporting a vulnerability

Please do not open a public issue. Email **support@yusuftuncel.tr** with the details and, if possible, a minimal fake sample that reproduces the problem. Never send real HTS records.
