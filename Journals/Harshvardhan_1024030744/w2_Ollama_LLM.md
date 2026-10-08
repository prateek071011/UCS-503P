# Week 2: Open-Source LLM Environment and Ollama Model Setup

## Work Completed

During this week, I focused on setting up a local environment for running **open-source Large Language Models (LLMs)** on a MacBook. The main objective was to install the required development tools, configure **Ollama** for local inference, and set up coding-oriented models that can be used for programming and benchmark experimentation.

### Initial Environment Setup

The initial installation command provided for the setup was a Windows-specific `winget` command. Since the available system was **macOS**, I adapted the installation process to use **Homebrew**, the package manager suitable for macOS.

The main setup requirements were:

* Homebrew for package management.
* Xcode Command Line Tools for required development utilities.
* Ollama for local LLM inference.
* Local coding models for experimentation.

### Homebrew Installation


I installed Homebrew using its official installation script. During the installation, the system requested administrator authentication and installed the required **Xcode Command Line Tools**.

The installation also created the required Homebrew directories under `/opt/homebrew`.

After installation, Homebrew was added to the shell environment and verified successfully using:

```bash
brew --version
```

The installed Homebrew version was verified as:

```text
Homebrew 7.0.8
```

### Xcode Command Line Tools Setup

The Homebrew installation automatically detected that the **Xcode Command Line Tools** were required.

The tools were downloaded and installed through the macOS Software Update system.

The installation completed successfully, and the Command Line Tools were selected using:

```bash
xcode-select --switch /Library/Developer/CommandLineTools
```

This provided the development utilities required for Homebrew and subsequent software installation.

### Homebrew PATH Configuration

After Homebrew was installed, its environment was configured for the Z shell using:

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv zsh)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv zsh)"
```

This ensured that the `brew` command was available from the Terminal.

The configuration was verified successfully using:

```bash
brew --version
```

### Ollama Installation

After configuring Homebrew, I installed **Ollama**, a tool for running LLMs locally.

The installation was performed using:

```bash
brew install ollama
```

Ollama and its required dependencies were downloaded and installed successfully.

The installed Ollama version was:

```text
0.40.0
```

### Ollama Service Configuration

After installation, Ollama was configured as a background service using:

```bash
brew services start ollama
```

The service started successfully with the label:

```text
sh.brew.ollama
```

The Ollama installation was therefore configured to run as a background service.

### Llama 3.2 Model Setup

To verify that the local Ollama environment was working correctly, I downloaded and ran the **Llama 3.2** model.

The model was started using:

```bash
ollama run llama3.2
```

The model downloaded successfully 

### DeepSeek Coder V2 Setup

After successfully testing Llama 3.2, I installed a larger coding-focused model, **DeepSeek Coder V2 16B**.

The model was downloaded using:

```bash
ollama pull deepseek-coder-v2:16b
```

The model download completed successfully.

The downloaded model size was approximately **8.9 GB**.

The model was then started using:

```bash
ollama run deepseek-coder-v2:16b
```

The successful appearance of:

```text
>>> Send a message
```

confirmed that DeepSeek Coder V2 16B was ready for local inference.

### Model Management

The installed Ollama models can be checked using:

```bash
ollama list
```

The local environment now contains both:

* **Llama 3.2**
* **DeepSeek Coder V2 16B**

Models can be started whenever required using:

```bash
ollama run llama3.2
```

or:

```bash
ollama run deepseek-coder-v2:16b
```

### Local Inference Workflow

The completed local workflow is:

**Programming Problem → Prompt → Ollama → Selected Local LLM → Generated Response/Code → Testing and Evaluation**

For coding experiments, DeepSeek Coder V2 16B can be used as the primary coding-oriented model, while Llama 3.2 can be used for general-purpose local LLM testing.

### Initial Testing

The local models were tested through interactive programming prompts.

The testing verified:

* The models could be downloaded successfully.
* Ollama could run the models locally.
* The models accepted natural-language prompts.
* The models could generate programming explanations and code.
* The local inference environment was ready for further experimentation.

### Key Observation

The setup demonstrated that open-source LLMs can be run locally without depending entirely on external cloud-based inference services.

Using Ollama also makes it possible to switch between different models while maintaining a common local inference interface.

The availability of both a general-purpose model and a coding-focused model provides a useful environment for comparing their performance on programming tasks.

## Outcome

By the end of the week:

* Adapted the original Windows-specific installation approach for **macOS**.
* Installed **Xcode Command Line Tools**.
* Installed and configured **Homebrew**.
* Configured the Homebrew environment in the Z shell.
* Verified Homebrew installation successfully.
* Installed **Ollama 0.40.0**.
* Configured Ollama as a background service.
* Downloaded and configured **Llama 3.2**.
* Successfully tested Llama 3.2 through interactive prompts.
* Downloaded **DeepSeek Coder V2 16B** using Ollama.
* Verified the successful 8.9 GB DeepSeek model download.
* Successfully launched **DeepSeek Coder V2 16B**.
* Established a local LLM environment for coding and experimentation.
* Prepared the system for further local model testing and coding benchmark experiments.
