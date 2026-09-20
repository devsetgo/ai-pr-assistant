# Changelog

All notable changes to this project will be documented in this file.

## Latest Changes
### 26.09.20-002

_Changes since 26.09.20-001._

#### What's Changed
* CI improvements: actions are now pinned to SHAs and Docker image dependencies are hash-locked

Generated Date: 2026 September 20, 19:02

### 26.09.20-001

#### What's Changed
* Add Claude provider, attribution footer, and GPT-6 support
* Refactor: drop the unused temperature parameter from the Claude path
* Add changelog automation, docs tooling, and demo sections for BumpCalver and pydantic-schemaforms
* Adopt Zensical docs with GitHub Pages workflow; document the Pages setting and state that the max_tokens default rose from 1000 to 2000
* Declare mypy, raise dev-dependency floors, add ruff + pre-commit, and improve repo hygiene (e.g., .dockerignore, changelog symlink, footer license, gitignore bumpcalver's local backups)
* Migrate Release Drafter to v7 layout and add Release Drafter workflow/config
* Run the docs build on PRs/pushes and deploy from its artifact
* Fix: honor sample_prompt/sample_response and clarify error handling
* Add SonarCloud quality badges, HTML coverage, BumpCalver versioning, and Dependabot
* Track sonar.projectVersion via BumpCalver and flesh out sonar-project.properties
* Add CLAUDE.md, License section, and Python 3.14 devcontainer
* Rebrand hard fork as ai-pr-assistant, split docs, update license, and reframe as inspired-by
* Make the dogfood workflow a full showcase of every action input, keep title/description/labels refreshed, enable labels, and grant additional permissions (pull-requests:write, issues:write)
* Add explicit Dependabot guard to the dogfood workflow
* Raise default max_tokens and guard against empty generated descriptions
* Stop mounting the retry adapter on http:// (fixes SonarCloud S5332)
* Fix GPT-5 request params, restructure into a package, add opt-in features, and use gpt-5 model by default
* Support AzureOpenAI client and use the latest openai Python module
* Use gpt-4o-mini (cheaper and better)
* Allow users to opt-in for existing PR description overwrite and customize the completion prompt
* Migrate to OpenAI v1 library
* Add pr-description action
* Various documentation, naming, and clarity improvements (README, argument order, error explanations, debug info, and house style)
* Update Dockerfile and bump Docker base image/pinned GitHub Actions
* Initial project presentation, setup, and Python script improvements

Generated Date: 2026 September 20, 17:59

### 26.09.19-002

_Changes since 26.09.19-001._

#### What's Changed
* ci: migrate Release Drafter to the v7 layout (separate autolabeler, `when` categories)
* ci: run the docs build on PRs and pushes again, and deploy from its artifact
* docs: state that the max_tokens default rose from 1000 to 2000
* fix: honor sample_prompt/sample_response and make error handling clearer
* chore: tidy docs and repo hygiene (.dockerignore, changelog symlink, footer license)
* chore: gitignore bumpcalver's local backups and history

Generated Date: 2026 September 19, 19:17

### 26.09.19-001

#### What's Changed
* Add ruff + pre-commit, a full `make test` gate, and a README-sourced docs index
* Add changelog automation and docs tooling
* Adopt Zensical docs with GitHub Pages workflow
* Add SonarCloud quality badges, HTML coverage, and BumpCalver versioning
* Add Release Drafter workflow and config
* Add CLAUDE.md (with License section) and a Python 3.14 devcontainer
* Track sonar.projectVersion via BumpCalver, flesh out sonar-project.properties
* Bump Docker base image and update pinned GitHub Actions
* Add explicit Dependabot guard to the dogfood workflow
* Disable moby in the devcontainer's docker-in-docker feature
* Rebrand hard fork as ai-pr-assistant, split docs, update license, and reframe as inspired-by
* Add pr-description action and changelog automation
* Migrate to OpenAI v1 library and use latest openai Python module
* Use gpt-5 model by default, support AzureOpenAI client, and add gpt-4o-mini option
* Fix GPT-5 request params, restructure into a package, add opt-in features
* Allow users to customize the completion prompt and opt-in for existing PR description overwrite
* Make the dogfood workflow a full showcase of every action input, enable labels, and refresh title/description/labels on every push
* Grant pull-requests:write and issues:write to the dogfood workflow, explain how to solve potential 403 error
* Give structured-mode title/description a consistent house style
* Raise default max_tokens and guard against empty generated descriptions
* Stop mounting the retry adapter on http:// (fixes SonarCloud S5332)
* Update Dockerfile and various documentation
* General improvements: renaming, rewording, presenting the project, argument ordering, and code cleanup
* Initial commit and foundational action implementation

Generated Date: 2026 September 19, 17:45

