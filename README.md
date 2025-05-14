# Obsidian Daily Analysis

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

> AI-powered project extraction and analysis for your Obsidian notes, automatically integrated into your daily notes workflow.

## Overview

Obsidian Daily Analysis is a Python tool that extends your Obsidian note-taking experience by identifying actionable projects throughout your vault and providing intelligent suggestions and resources for them. It seamlessly integrates with your Daily Notes workflow, so you always start each day with an analysis of the important projects discovered in your notes from the previous day.

## Features

- 🔍 **Intelligent Project Extraction**: Automatically identifies actionable projects hidden in your notes, distinguishing them from simple tasks or philosophical musings
- 🧠 **AI-Powered Analysis**: Provides tailored suggestions and relevant resources for each project
- 📝 **Daily Notes Integration**: Seamlessly appends analysis to your daily notes, following your existing templates
- 🔄 **Flexible LLM Support**: Works with both Ollama (local) and OpenAI (cloud) language models
- ⚙️ **Highly Configurable**: Customize paths, models, templates, and more through YAML configuration
- 🏃 **Automation-Ready**: Perfect for automation through cron jobs, scheduled tasks, or Obsidian plugin integrations

## Why Use Obsidian Daily Analysis?

### Find the Signal in the Noise

Your notes contain a wealth of ideas, but many actionable projects can get lost among daily tasks and reflections. Obsidian Daily Analysis uses AI to distinguish meaningful projects from simple tasks or philosophical musings.

### Start Each Day Focused

Begin each day with a clear overview of projects extracted from your recent notes, complete with concrete next steps and resources to move forward. No more losing track of important ideas.

### Private and Flexible

- **Private First**: Run completely locally using Ollama with open-source models (like Gemma)
- **Cloud Option**: Alternatively, use OpenAI's models for more advanced analysis
- **Your Data, Your Choice**: Full control over which folders are analyzed

### How It's Different 

- **Focus on Projects**: Unlike task extractors, this tool specifically finds *actionable projects* - the complex, multi-step initiatives that benefit most from structured analysis
- **Seamless Integration**: Works directly with your existing daily notes template, without requiring special syntax or frontmatter
- **Works with Your Workflow**: Requires no special note structure or tagging system - just write notes naturally
- **Local-First**: Designed to work completely offline with local models, unlike most AI assistants

## Installation

### Prerequisites

- Python 3.8 or higher
- [Ollama](https://ollama.com/) (if using local models) or an OpenAI API key

### Step 1: Clone the repository

```bash
git clone https://github.com/undergroundpost/obsidian-daily-analysis.git
cd obsidian-daily-analysis
```

### Step 2: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure settings

Copy the example configuration file and edit it to match your Obsidian vault structure:

```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml` to customize:
- Input/output folder paths
- LLM provider settings
- Daily note format

## Usage

### Basic Usage

Run the script to analyze notes from the previous day:

```bash
python generate_analysis.py
```

### Advanced Options

```bash
# Process notes from a specific date
python generate_analysis.py --date 2024-05-13

# Use a specific LLM provider
python generate_analysis.py --provider openai --api-key your_openai_key

# Override folder locations
python generate_analysis.py --input "/path/to/vault" --daily "/path/to/daily/notes"

# Add delay between API calls (helpful for API rate limits)
python generate_analysis.py --delay 2

# Enable debug logging
python generate_analysis.py --debug
```

### Automated Execution

For best results, set up a scheduled task or cron job to run the script every morning before you start your day.

#### Example cron entry (runs daily at 5 AM):

```
0 5 * * * cd /path/to/obsidian-daily-analysis && python generate_analysis.py >> ~/.obsidian-daily-analysis.log 2>&1
```

## Configuration

The `config.yaml` file allows you to customize various aspects of the tool:

```yaml
# Folder settings
INPUT_FOLDER: "/path/to/your/vault"        # Main notes folder
EXCLUDE_FOLDERS:                           # Folders to exclude
  - "/path/to/your/vault/AI"
  - "/path/to/your/vault/Archive"

# Daily notes settings
DAILY_NOTES_FOLDER: "/path/to/your/vault/Daily Notes"   # Where daily notes are stored
DAILY_NOTE_TITLE_FORMAT: "%Y-%m-%d"                     # Format for daily note filenames
DAILY_NOTE_TEMPLATE_PATH: "/path/to/your/template.md"   # Optional template file

# Analysis settings
ANALYSIS_HEADER: "# Yesterday's Analysis"               # Header where analysis will be appended

# LLM Provider settings (choose one)
LLM_PROVIDER: "ollama"                                  # Options: "ollama" or "openai"

# Ollama settings
OLLAMA_MODEL: "gemma3:12b"                              # Ollama model to use
OLLAMA_SERVER_ADDRESS: "http://localhost:11434"         # Ollama server address
OLLAMA_CONTEXT_WINDOW: 32000                            # Context window size

# OpenAI settings
OPENAI_API_KEY: ""                                      # Your OpenAI API key
OPENAI_MODEL: "gpt-4"                                   # OpenAI model to use
OPENAI_MAX_TOKENS: 4000                                 # Maximum tokens for responses
```

## How It Works

1. **File Discovery**: Identifies notes created or modified on the previous day
2. **Content Extraction**: Cleans note content, removing templates and dataview blocks
3. **Project Identification**: Uses AI to distinguish actionable projects from simple tasks
4. **Analysis Generation**: Creates custom suggestions and resource recommendations for each project
5. **Daily Note Integration**: Automatically appends the analysis to today's daily note

## Customizing the AI Prompts

You can modify the extraction and analysis prompts to fit your specific needs:

- `extract_projects.md`: Controls how projects are identified and extracted
- `generate_analysis.md`: Defines how suggestions and resources are generated

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built for the Obsidian community
- Inspired by the power of AI to enhance knowledge management

---

Created by [undergroundpost](https://github.com/undergroundpost)
