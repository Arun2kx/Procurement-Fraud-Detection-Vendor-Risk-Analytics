# Notice

ProcureGuard is an original analytics project created for portfolio review. The generator, screening rules, SQL, scoring model, tests, and documentation in this repository were written for this project.

All procurement records shipped with the repository, and all records produced by `python -m src.pipeline generate`, are synthetic. They must not be described as real vendors, real employees, confirmed fraud, or real financial loss. Synthetic GSTINs and bank-account hashes are not usable identifiers.

The detection output is a screening worklist. Review status starts at Pending Review. A risk score is an explainable weighted index, not a probability of fraud and not a finding that has been confirmed by an auditor.

# License

MIT License

Copyright (c) 2026 the ProcureGuard repository author

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
