# Operation Reuse

Sometimes several implementation steps are so tightly coupled that treating them as separate operations makes later analysis ambiguous. In that case, you can reuse one operation record across multiple dependency edges.

This page shows a common example: a Large Language Model (LLM) produces a JSON-like string, and a JSON parsing function turns that string into a Python object. If parsing fails, it may be unclear whether the root cause is the LLM generation step or the JSON parsing step. For example, an LLM may produce text that is very close to the expected format but contains an escaping issue, such as a LaTeX command like `"\frac"` that is not escaped correctly for JSON. Improving the prompt or model generation may fix the issue. Improving the parser or repair logic may also fix the issue.

If you later want to automatically locate faulty operations and evaluate the result, splitting this coupled behavior into two separate operations may create unnecessary disputes. In such cases, it is often better to merge them into one logical operation.

---

## 1. A Coupled LLM-Parsing Example

In the example below, `dummy_llm` returns a JSON-like response, and `parse_llm_json` parses it. We trace both steps under the same operation.

```python
import json
from smartcomment import (
    comment_graph,
    comment_op,
    comment_op_scope,
    comment_variable,
)


def dummy_llm(prompt: str) -> str:
    """Return a JSON-like response from a dummy LLM."""
    return r'{"answer": "smartcomment can trace LLM output with \\frac{a}{b}."}'


def parse_llm_json(raw_response: str) -> dict[str, str]:
    """Parse an LLM response into a Python dictionary."""
    return json.loads(raw_response)


def extract_answer(prompt: str) -> dict[str, str]:
    """Generate and parse an LLM response as one logical operation."""
    prompt = comment_variable(
        prompt,
        category="prompt",
        comment="The prompt sent to the dummy LLM.",
    )

    with comment_op_scope(
        op_name="llm_json_extraction",
        category="llm_json_extraction",
        comment=(
            "Generate a JSON-like LLM response and parse it into a structured "
            "Python object."
        ),
    ):
        raw_response = dummy_llm(prompt)
        raw_response = comment_variable(
            raw_response,
            category="llm_response",
            comment="The raw JSON-like response returned by the dummy LLM.",
        )
        comment_op(
            inputs=[prompt],
            outputs=[raw_response],
            category="llm_generation",
            comment="Generate a JSON-like response from the prompt.",
            reuse_op=True,
        )

        parsed_response = parse_llm_json(raw_response)
        parsed_response = comment_variable(
            parsed_response,
            category="parsed_response",
            comment="The parsed Python dictionary from the raw LLM response.",
        )
        comment_op(
            inputs=[raw_response],
            outputs=[parsed_response],
            category="json_parsing",
            comment="Parse the raw LLM response into a Python dictionary.",
            reuse_op=True,
        )

    return parsed_response
```

**The important part is `reuse_op=True`**. The surrounding `comment_op_scope` creates one active operation record, and each `comment_op(..., reuse_op=True)` adds edges that reuse that active operation instead of creating a new one.

Run the function inside a graph and print the whole graph as Markdown:

```python
with comment_graph() as graph:
    parsed_response = extract_answer(
        "Return a JSON object with an answer that may contain a LaTeX formula."
    )

print(graph.to_runtime_graph().to_markdown())
```

The output is:

```text
## Graph

### Nodes (3)

**str:8ec7e3e8663b8f05cb6fb29dbf4debd5747450e3** (v1)
- Full Node ID: `str:8ec7e3e8663b8f05cb6fb29dbf4debd5747450e3@1`
- Value: `'Return a JSON object with an answer that may contain a LaTeX formula.'`
- Comment: The prompt sent to the dummy LLM.
- Category: prompt
- Created At: created in the system at `2026-06-01 17:44:07.753`

**str:00ed4af3c4e1a190a1beba891400c6cf8b6cc901** (v1)
- Full Node ID: `str:00ed4af3c4e1a190a1beba891400c6cf8b6cc901@1`
- Value: `'{"answer": "smartcomment can trace LLM output with \\\\frac{a}{b}."}'`
- Comment: The raw JSON-like response returned by the dummy LLM.
- Category: llm_response
- Created At: created in the system at `2026-06-01 17:44:07.773`

**dict:49efe408116cb643649e73f2718f311b58f90930** (v1)
- Full Node ID: `dict:49efe408116cb643649e73f2718f311b58f90930@1`
- Value: `{'answer': 'smartcomment can trace LLM output with \\frac{a}{b}.'}`
- Comment: The parsed Python dictionary from the raw LLM response.
- Category: parsed_response
- Created At: created in the system at `2026-06-01 17:44:07.785`

### Edges (2)

**Edge: `str:8ec7e3e8663b8f05cb6fb29dbf4debd5747450e3@1` -> `str:00ed4af3c4e1a190a1beba891400c6cf8b6cc901@1`**
- Edge ID: `edge-708d07b27ad44e8aa9f63a65577a1ed9`
- Category: llm_generation
- Comment: Generate a JSON-like response from the prompt.
- Created At: created in the system at `2026-06-01 17:44:07.779`

**Edge: `str:00ed4af3c4e1a190a1beba891400c6cf8b6cc901@1` -> `dict:49efe408116cb643649e73f2718f311b58f90930@1`**
- Edge ID: `edge-f95baf9e973c44788b97e1124705b697`
- Category: json_parsing
- Comment: Parse the raw LLM response into a Python dictionary.
- Created At: created in the system at `2026-06-01 17:44:07.791`

### Operations (1)

**Op: llm_json_extraction**
- Operation ID: `op-aec4913b48bd4eb692ed8076832c269a`
- Category: llm_json_extraction
- Comment: Generate a JSON-like LLM response and parse it into a structured Python object.
- Created At: created in the system at `2026-06-01 17:44:07.767`
```

**Do not overuse operation reuse. If two steps have clearly separable responsibilities and you want to attribute failures to one of them, keep them as separate operations. Reuse is most helpful when splitting the steps would make failure attribution arbitrary or controversial**.

---

**Next:** [In-Place Operation →](in_place_operation.md)
