# PS5 NID Database
 
**A searchable catalog of PlayStation 5 NIDs (Name IDentifiers), comparing their implementation status across the main open-source emulator projects.**
 
[![License: GPL-2.0-only](https://img.shields.io/badge/license-GPL--2.0--only-blue.svg)](#-license)
[![Live site](https://img.shields.io/badge/live%20site-ekt0re.github.io-6e8efb.svg)](https://ekt0re.github.io/PS5-NID-DB/)
[![Repository](https://img.shields.io/badge/GitHub-Ekt0re%2FPS5--NID--DB-181717?logo=github)](https://github.com/Ekt0re/PS5-NID-DB)
 

---
 
## 📑 Table of contents
 
- [About the project](#-about-the-project)
- [Features](#-features)
- [How to find where a NID is implemented](#how-to-find-where-a-nid-is-implemented)
- [API](#-api)
- [Important disclaimers](#️-important-disclaimers)
- [AI-assisted development](#-ai-assisted-development)
- [Legal notes](#️-legal-notes)
- [Contributing](#-contributing)
- [Acknowledgements](#-acknowledgements)
- [License](#-license)
---
 
## 📖 About the project
 
PS5 system libraries expose their functions through **NIDs**: identifiers (hashes) that replace function names in binaries. Emulator developers need to map each NID to its function and implement it.
 
**PS5 NID Database** gathers in one place the data published by these repositories:
 
| Project | Repository |
|---------|------------|
| **AnyPS5** | [boykopovar/AnyPS5](https://github.com/boykopovar/AnyPS5) |
| **KytyPS5** | [KytyPS5/KytyPS5](https://github.com/KytyPS5/KytyPS5) |
| **SharpEmu** | [sharpemu/sharpemu](https://github.com/sharpemu/sharpemu) |
 
and compares them, showing for each function and each NID:
 
- which **library** it belongs to;
- whether it is **implemented**, a **stub** (present but not actually implemented), or **not implemented / unknown** in each project;
- a **direct link to the exact point in the source code** where it is implemented (file and line).
The site also includes global statistics (number of functions, NIDs, libraries), progress bars for each emulator, and a chart showing progress over time.
 
---
 
## 🔎 Features
 
| | Feature | Description |
|---|---------|-------------|
| 🔍 | **Search** | Look up by NID or function name (press `/` to focus the search bar). |
| 🎛️ | **Filters** | Filter by library, emulator, and implementation status. |
| 📄 | **Detail view** | Per-function status in each emulator. |
| 🔗 | **Source link** | Opens the original repository at the exact file and line of the implementation. |
| 📊 | **Statistics** | Global counts and progress percentages for each project. |
| 📈 | **History chart** | Implementation progress over time. |
| 🌗 | **Themes** | Light and dark mode. |
| ⚙️ | **JSON API** | Query a single NID programmatically (see [API](#-api)). |
 
Example of a source reference:
 
```
core/libs/prx/libSceAgc/Cb/src/Registers.cpp:43
```
 
### How to find where a NID is implemented
 
1. Paste a NID (e.g. `yUBESvCCJ4I`) or a function name into the search bar.
2. Select the result from the list on the left.
3. In the detail panel, check the status for **AnyPS5**, **KytyPS5**, and **SharpEmu**.
4. Click **source** to open the exact code in the project's repository.
---
 
## ⚙️ API
 
Given a NID, the API returns a JSON document with its data.
 
```
https://ekt0re.github.io/PS5-NID-DB/api/<NID>.json
```
 
**Example:** [`https://ekt0re.github.io/PS5-NID-DB/api/yUBESvCCJ4I.json`](https://ekt0re.github.io/PS5-NID-DB/api/yUBESvCCJ4I.json)
 
```bash
curl https://ekt0re.github.io/PS5-NID-DB/api/yUBESvCCJ4I.json
```
 
---
 
## ⚠️ Important disclaimers
 
> [!WARNING]
> The data in this project is **approximate** and may contain **errors**. Always verify against the original source code.
 
### Data accuracy
 
- The data is **an approximation**. It is extracted automatically from the repositories listed above and is **not manually verified** entry by entry.
- The "implemented", "stub", or "not implemented" status is inferred from code analysis: a function marked as *implemented* may actually be incomplete, partial, or non-functional, and vice versa.
- Percentages, counts, and charts are **indicative only** and are not an official measure of an emulator's compatibility or quality.
### Search and matching algorithm
 
- Search and the association between NIDs, function names, and source code rely on a **heuristic algorithm that can make mistakes**: false positives, false negatives, and links to wrong or outdated files or lines.
- Some NIDs may be associated with multiple names, with wrong names, or not associated at all.
- Source links point to a specific version of each repository: as the original projects evolve, **files and line numbers may change** and a link may no longer point to the correct location.
### Possible errors
 
- The project may contain **errors, omissions, and outdated information**.
- Do not rely on this data for critical decisions. Always verify against the original source code.
- If you find a mistake, **open an Issue** or submit a **Pull Request**. All reports are welcome.
---
 
## 🤖 AI-assisted development
 
This project was **developed with the support of artificial intelligence** (code, structure, interface, and documentation, including this README). The generated code was reviewed and integrated by the author but, as with any software built with AI tools, **it may contain bugs, inaccuracies, or suboptimal choices**. Contributions and reviews are welcome.
 
---
 
## ⚖️ Legal notes
 
- **No affiliation.** This project is independent and is **not affiliated with, sponsored by, or endorsed by** Sony Interactive Entertainment, PlayStation, or the authors of AnyPS5, KytyPS5, or SharpEmu.
- **Trademarks.** "PlayStation", "PS5", and related logos are registered trademarks of Sony Interactive Entertainment Inc. All other trademarks belong to their respective owners. They are mentioned solely for identification and descriptive purposes.
- **No protected content.** This repository **does not contain, distribute, or promote**: firmware, BIOS, cryptographic keys, games, copyrighted files, or tools to circumvent protections or enable piracy.
- **Third-party data.** The project contains only **metadata** (identifiers, function names, implementation statuses, file and line references) derived from public repositories. The original source code remains the property of its respective authors and is subject to the **licenses of the original repositories**. Please consult those licenses for any use of their code.
- **Purpose.** The project is intended **solely for informational, educational, and research / interoperability purposes**.
- **No warranty.** The software and data are provided **"as is"**, without warranties of any kind, express or implied, including accuracy, completeness, merchantability, or fitness for a particular purpose. The author is not liable for any damages arising from the use of the project or its data.
- **Takedown.** If you are a rights holder and believe that content in this repository infringes your rights, open an Issue or contact the author: it will be reviewed and promptly removed if appropriate.
---
 
## 🤝 Contributing
 
1. Fork the repository.
2. Create a branch for your change (`git checkout -b fix/change-name`).
3. Commit and push your changes.
4. Open a Pull Request describing the change.
You can also contribute by reporting incorrectly matched NIDs, broken source links, or improvements to the search algorithm.
 
---
 
## 🙏 Acknowledgements
 
Thanks to the teams and contributors of the open-source projects the data comes from:
 
| Project | License |
|---------|---------|
| **AnyPS5** | GPL-2.0-only |
| **KytyPS5** | GPL-2.0-only, based on [Kyty](https://github.com/InoriRus/Kyty) by InoriRus (MIT) |
| **SharpEmu** | GPL-2.0 |
 
This catalog would not be possible without their public work.
 
---
 
## 📄 License
 
This project is released under the **GPL-2.0-only** license.
