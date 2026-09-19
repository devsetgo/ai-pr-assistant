# Changelog

All notable changes to this project will be documented in this file.

## Latest Changes
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

