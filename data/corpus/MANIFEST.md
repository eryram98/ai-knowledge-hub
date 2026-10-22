# Corpus manifest

Every document in `data/corpus/<kb_id>/` must be public and listed here. The files
themselves are git-ignored; this list lets anyone rebuild the corpus by downloading
from the URLs.

| Title | File | URL | KB | Downloaded on |
|---|---|---|---|---|
| Raspberry Pi Pico Datasheet | `hw_datasheets/pico-datasheet.pdf` | https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf | hw_datasheets | 2026-10-20 |
| Raspberry Pi Pico 2 Datasheet (RP-008299-DS-3) | `hw_datasheets/RP-008299-DS-3-pico-2-datasheet.pdf` | | hw_datasheets | 2026-10-22 |
| Raspberry Pi Pico W Datasheet (RP-008312-DS-2) | `hw_datasheets/RP-008312-DS-2-pico-w-datasheet.pdf` | | hw_datasheets | 2026-10-22 |
| Raspberry Pi 5 Product Brief (RP-008348-DS-8) | `hw_datasheets/RP-008348-DS-8-raspberry-pi-5-product-brief.pdf` | | hw_datasheets | 2026-10-22 |
| RP2040 Datasheet (RP-008371-DS-1) | `hw_datasheets/RP-008371-DS-1-rp2040-datasheet.pdf` | | hw_datasheets | 2026-10-22 |
| Raspberry Pi Microcontrollers Product Guide (RP-009950-MM-1) | `hw_datasheets/RP-009950-MM-1-Raspberry Pi Microcontrollers product guide.pdf` | | hw_datasheets | 2026-10-22 |
| Procedures for Obtaining Access to User Data (Process_UserData) | `it_policies/Process_UserData.pdf` | | it_policies | 2026-10-22 |
| Policies Pyramid: Policy, Standards, Procedures, Guidelines (policiespyramidnew) | `it_policies/policiespyramidnew.pdf` | | it_policies | 2026-10-22 |
| UTDBP3096 Information Security and Acceptable Use Policy (policy-utdbp3096) | `it_policies/policy-utdbp3096.pdf` | | it_policies | 2026-10-22 |

URLs left blank are unknown: fill them in from where each file was downloaded. The policy files
are UT Dallas documents (the text names UT Dallas and its Information Security Office).

Not indexed: `RP-008348-DS-8-raspberry-pi-5-product-brief.pdf` (52.9 MB) is over the 25 MB upload
limit (`INGESTION_MAX_FILE_SIZE_MB`) and was rejected with `file_too_large` on 2026-10-22.
