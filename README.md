# nlhe-solves

Runs the open-source [GTOpen](https://github.com/MatthewPDingle/GTOpen) solver (Apache-2.0) on GitHub Actions and
keeps the solved no-limit hold'em trees as build artifacts. `games/*.json` are GTOpen preflop configs;
`probe.py` builds one, solves it and dumps every decision it can reach.
