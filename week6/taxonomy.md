# Week 6 Evaluation Taxonomy

Built from 35 distinct real traces labeled before the next LLM-judge run.

| Mode | Count | Frequency | Severity | Example trace ID |
|---|---:|---:|---|---|
| correct answer supported | 17 | 48.6% | None | `198b1e2a414041b7a2488491bb28af76` |
| gorouter question abstention | 7 | 20.0% | Blocks developer task | `7ab995134750405bb2bacc385091c67f` |
| firebase auth question abstention | 6 | 17.1% | Blocks developer task | `ee45c541fcb54652a28b0e92bc428d16` |
| appropriate abstention for missing evidence | 2 | 5.7% | None | `bcb1d56f7c0e49489b183442584d9116` |
| dio connection timeout answer uses receive timeout | 1 | 2.9% | Ships broken code | `6ea11b46a8ca4f94afe33858da825bb7` |
| dio authorization header abstention | 1 | 2.9% | Blocks developer task | `2b96b09d958e4dcd88de845f133e89b9` |
| missing dio version warning | 1 | 2.9% | Ships broken code | `09808a6aca0341b09bbdb37a805f3262` |

**Total: 35 traces (100%).**
