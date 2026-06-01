## smartcomment

`smartcomment` is a lightweight Python tracing toolkit for recording execution graphs from existing systems. It lets developers annotate variables, operations, and dependencies without reorganizing the original program.

The package is designed for systems that maintain complex state over time, such as multi-agent systems, memory systems, and data workflows. Instead of only recording events or function calls, `smartcomment` records how variables flow through developer-specified operations, making the resulting trace useful for visualization, program understanding, and failure attribution.

### Installation

Install the core package:

```bash
pip install smartcomment
```

Install optional visualization dependencies:

```bash
pip install smartcomment[viz]
```

For local development from source:

```bash
git clone https://github.com/zjunlp/smartcomment.git
cd smartcomment
pip install -e .
```

### Quick Example

```python
from smartcomment import comment_fn, comment_graph


@comment_fn(
    op_name="demo.generate",
    comment="Generate a response from a user query.",
    category="generation",
)
def generate_response(query: str) -> str:
    return "smartcomment records execution graphs."


with comment_graph() as graph:
    response = generate_response("What does smartcomment do?")

print(graph.to_runtime_graph().to_markdown())
```

### Documentation

The repository includes a set of focused guides under [`docs/`](docs/).

### Citation

If you use `smartcomment` in your work, please cite:

```bibtex
@misc{deng2026memtracetracingattributingerrors,
      title={MemTrace: Tracing and Attributing Errors in Large Language Model Memory Systems}, 
      author={Xinle Deng and Ruobin Zhong and Hujin Peng and Xiaoben Lu and Yanzhe Wu and Guang Li and Buqiang Xu and Yunzhi Yao and Jizhan Fang and Haoliang Cao and Junjie Guo and Yuan Yuan and Ziqing Ma and Yuanqiang Yu and Rui Hu and Baohua Dong and Hangcheng Zhu and Ningyu Zhang},
      year={2026},
      eprint={2605.28732},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2605.28732}, 
}
```

### License

This project is released under the MIT License.
