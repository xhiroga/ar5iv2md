# ar5iv2md

Get arXiv in Markdown through ar5iv.

## How to use

```sh
$ uvx --from git+https://github.com/xhiroga/ar5iv2md ar5iv2md https://ar5iv.org/html/1706.03762 --download-dir out

out/1706.03762/README.md

# URL format is flexible. ex)
#  - 2010.11929, 2010.11929v2
#  - math/0301234, astro-ph/9901234v1
#  - arXiv:2010.11929v2
#  - https://arxiv.org/abs/2010.11929v2
#  - https://arxiv.org/pdf/2010.11929v2.pdf
#  - https://arxiv.org/html/2503.21408v1
$ uvx --from git+https://github.com/xhiroga/ar5iv2md ar5iv2md 2010.11929 --download-dir out

out/2010.11929/README.md
```
