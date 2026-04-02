# External evaluation sources

The BFCL repository is intentionally not vendored into this project. Recreate it with:

```powershell
git clone --depth 1 --filter=blob:none --sparse https://github.com/EnlightenedAI/BFCL.git evaluation/external/BFCL
git -C evaluation/external/BFCL sparse-checkout set berkeley-function-call-leaderboard/bfcl_eval/data
```

The local evaluation scripts consume a small slice of `BFCL_v4_simple_python.json`.
