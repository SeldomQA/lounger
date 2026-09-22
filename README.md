# lounger

**English** | [简体中文](./README.zh-CN.md)


![](./images/logo-no-background.png)

Next generation automated testing framework. Supports API, Web, and AI automated testing.

`Lounger` is an integrated automation testing framework built on `pytest`. It simplifies API and Web UI testing and combines AI integrations with project scaffolding to help developers and test engineers build reliable, extensible test suites.

---

## ✨ Key Features

* **🛠️ Ready-to-use scaffolding**: Create API or Web automation projects with the `lounger` CLI.
* **🌐 Integrated ecosystem**: Combine plugins such as `pytest-playwright`, `pytest-req`, and `pytest-xhtml` to cover multiple testing scenarios in one framework.
* **🤖 AI-powered testing**: Integrate AI agents for action-oriented automation and reduce maintenance as user interfaces change.
* **📊 Enhanced reports**: Generate customized HTML reports with execution logs, screenshots, and assertion details.
* **⚡ Parallel execution**: Run tests concurrently with `pytest-xdist`.
* **💾 Data-driven testing and caching**: Use YAML/JSON test data and share cached values across test cases.
* **💻 Web Runner**: Manage and run test cases through a browser-based workbench.

---

## 🏗️ Architecture

The framework has three layers, covering test authoring, execution, and results:

1. **Built-in capabilities**: Data-driven testing, project scaffolding, database operations, notifications, caching, random data generation, environment configuration, and utilities.
2. **Ecosystem integrations**: `pytest-req` for HTTP requests and assertions, `pytest-xhtml` for HTML reports, `auto-wing` for AI automation, and Web Runner for test cases, tasks, logs, and run history. `pytest-playwright`, `pytest-rerunfailures`, and `pytest-xdist` provide Web UI automation, retries, and parallel execution.
3. **Test execution foundation (pytest)**: Test discovery, fixtures, parametrization, plugin hooks, and execution lifecycle management.

Install database drivers and dependencies for AI, Web UI automation, and parallel execution as needed.

![Lounger architecture: built-in capabilities, ecosystem integrations, and the pytest execution foundation](./images/framework.png)

[SVG diagram](./images/framework.svg) · [Editable draw.io source](./images/framework.drawio)

---

## 🚀 Quick Start

### Installation

Install lounger:

```bash
pip install lounger
```

Install the latest code from the repository:

```bash
pip install -U git+https://github.com/SeldomQA/lounger.git@main
```

View the available `lounger` commands:

```text
$ lounger --help
Usage: lounger [OPTIONS] COMMAND [ARGS]...

  lounger — next generation automated testing framework.

  Examples:
    lounger --project-web myproject
    lounger --project-api myproject
    lounger runner --port 5002 --project ./myapi

Options:
  --version                Show version.
  -pw, --project-web TEXT  Create a Web automation test project.
  -pa, --project-api TEXT  Create an API automation test project.
  --help                   Show this message and exit.

Commands:
  runner  Start the web test runner.
```

### Create a Project

Generate a project with the scaffolding commands:

```bash
# Create a Web UI automation project
lounger --project-web myweb

# Create an API automation project
lounger --project-api myapi
```

## 🧪 Web Runner / Workbench

Use the browser-based runner to manage and execute your test cases.

```bash
# Enter your Web or API project directory
cd myapi
lounger runner
```

Open the URL printed by the runner in your browser. Press `Ctrl+C` to stop the service.

![Lounger Web Runner workbench](./images/lounger-runner-v2.png)

---

## Projects, Documentation, and Examples

1. How do I write Web automation tests? 👉 [Web project documentation](./myweb)
2. How do I write API automation tests? 👉 [API project documentation](./myapi)
3. What features does the framework provide? [Test examples](./samples)

---

## 🤝 Contributions and Feedback

If you have suggestions or find a bug, please open an [issue](https://github.com/SeldomQA/lounger/issues) or submit a pull request.

---
