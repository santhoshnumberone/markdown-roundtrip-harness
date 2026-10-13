# Inputs from Article 2

Both files are copied unchanged from https://github.com/santhoshnumberone/mutation-planner-harness.

| file | what it is | sha256 |
|---|---|---|
| `ast_reference.json` | the node list Article 2's planner view was built from | `bd34575b18189172187aa582f49c010878f364be187825cd350b118a8bf3af24` |
| `gold_set.json` | the ten test cases and their expected operations | `3c95116c443f7be92aeb83f20515afa52f970e2ba9b7959239294b58184e0f54` |

`tests/test_article2_inputs.py` checks that `examples/api_spec.md` is the document the reference was built
from, that this engine produces the same node ids, and that every node a gold operation targets exists here.
