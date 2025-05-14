#!/usr/bin/env python3
# Generate project analysis for Obsidian notes using AI (Ollama or OpenAI)
# Scans for notes created/modified on the previous day, extracts projects, analyzes them,
# and appends analysis to the current day's daily note

import os, sys, re, json, logging, requests, time, yaml
from datetime import datetime, timedelta
from pathlib import Path
from dateutil import parser

# Configure logger - will be properly initialized in __main__
logger = logging.getLogger(__name__)

def load_config():
    """Load configuration from YAML file with defaults"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Default configuration
    default_config = {
        "INPUT_FOLDER": os.path.expanduser("~/Documents/Notes"),
        "EXCLUDE_FOLDERS": [os.path.expanduser("~/Documents/Notes/AI")],
        "DAILY_NOTES_FOLDER": os.path.expanduser("~/Documents/Notes/Daily"),
        "DAILY_NOTE_TITLE_FORMAT": "%Y-%m-%d",
        "DAILY_NOTE_TEMPLATE": "",
        "ANALYSIS_HEADER": "## Yesterday's Analysis",
        "LLM_PROVIDER": "ollama", 
        "OLLAMA_MODEL": "gemma3:12b",
        "OLLAMA_SERVER_ADDRESS": "http://localhost:11434",
        "OLLAMA_CONTEXT_WINDOW": 32000,
        "OPENAI_API_KEY": "",
        "OPENAI_MODEL": "gpt-3.5-turbo",
        "OPENAI_MAX_TOKENS": 4000
    }
    
    # Check config file locations in priority order
    for config_path in [
        os.path.join(script_dir, "config.yaml"),
        os.path.expanduser("~/.config/generate_analysis/config.yaml"),
        "/etc/generate_analysis/config.yaml"
    ]:
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    user_config = yaml.safe_load(f) or {}
                    logger.info(f"Loaded configuration from {config_path}")
                    config = {**default_config, **user_config}
                    
                    # Handle backward compatibility
                    if "EXCLUDE_FOLDER" in user_config and "EXCLUDE_FOLDERS" not in user_config:
                        config["EXCLUDE_FOLDERS"] = [user_config["EXCLUDE_FOLDER"]]
                    
                    return config
            except Exception as e:
                logger.warning(f"Error loading config from {config_path}: {e}")
    
    logger.info("No config file found, using default configuration")
    return default_config

def get_previous_day_boundaries(override_date=None):
    """Get start/end time boundaries for previous day or specified date"""
    if override_date:
        try:
            target_date = parser.parse(override_date).date()
            logger.info(f"Using override date: {target_date}")
        except ValueError:
            logger.error(f"Invalid date format: {override_date}, using previous day")
            target_date = (datetime.now() - timedelta(days=1)).date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()
    
    start_boundary = datetime.combine(target_date, datetime.min.time())
    end_boundary = datetime.combine(target_date, datetime.max.time())
    
    logger.info(f"Target date: {target_date}")
    logger.info(f"Start/end boundaries: {start_boundary.date()} to {end_boundary.date()}")
    
    return start_boundary, end_boundary

def get_file_creation_time(file_path):
    """Get file creation time with platform-specific handling"""
    if sys.platform == 'darwin':  # macOS
        try:
            import subprocess
            result = subprocess.run(['stat', '-f', '%B', file_path], capture_output=True, text=True, check=True)
            return datetime.fromtimestamp(float(result.stdout.strip()))
        except Exception as e:
            logger.warning(f"Error getting macOS file creation time: {e}")
            return datetime.fromtimestamp(os.path.getctime(file_path))
    else:  # Windows/Linux
        return datetime.fromtimestamp(os.path.getctime(file_path))

def find_md_files_from_previous_day(input_folder, exclude_folders, start_boundary, end_boundary):
    """Find markdown files created/modified in the specified time range by humans (not by scripts)"""
    md_files = []
    skipped_files = 0
    
    logger.info(f"Searching for Markdown files in: {input_folder}")
    logger.info(f"Using date range: {start_boundary.date()} to {end_boundary.date()}")
    logger.info(f"Excluding folders: {exclude_folders}")
    
    for root, _, files in os.walk(input_folder):
        # Skip excluded folders
        if any(root.startswith(exclude_folder) for exclude_folder in exclude_folders):
            continue
            
        for file in files:
            if not file.endswith('.md'):
                continue
                
            file_path = os.path.join(root, file)
            file_ctime = get_file_creation_time(file_path)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
            
            logger.debug(f"File: {file_path}, Creation: {file_ctime}, Modified: {file_mtime}")
            
            # Check if the file's timestamp is in the specified range
            file_in_date_range = False
            if (start_boundary <= file_ctime <= end_boundary) or (start_boundary <= file_mtime <= end_boundary):
                file_in_date_range = True
                
                # Now check if it's been processed and not modified since
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    frontmatter, _ = parse_frontmatter(content)
                    
                    # If it has an analyzed timestamp, check if modified since
                    if 'analyzed' in frontmatter:
                        try:
                            analyzed_time = parser.parse(str(frontmatter['analyzed']))
                            # Use a 15-minute cooldown period to account for all automated scripts
                            cooldown_period = timedelta(minutes=15)
                            
                            # Add detailed logging to help troubleshoot
                            logger.debug(f"File: {os.path.basename(file_path)}")
                            logger.debug(f"  Last modified: {file_mtime}")
                            logger.debug(f"  Last analyzed: {analyzed_time}")
                            logger.debug(f"  Time difference: {(file_mtime - analyzed_time).total_seconds()/60:.2f} minutes")
                            
                            if file_mtime > (analyzed_time + cooldown_period):
                                # Modified after cooldown period - likely a human modification
                                logger.debug(f"  ✓ File modified after 15-minute cooldown: {file_path}")
                                md_files.append(file_path)
                            else:
                                # Modified within cooldown period - likely an automated script
                                logger.debug(f"  ✗ File modified within cooldown period (likely by script): {file_path}")
                                skipped_files += 1
                        except (ValueError, TypeError) as e:
                            logger.debug(f"  ! Error parsing analyzed time: {e}")
                            # Can't parse timestamp - include it to be safe
                            md_files.append(file_path)
                    else:
                        # No processed timestamp - include it
                        logger.debug(f"No analysis timestamp, including file: {file_path}")
                        md_files.append(file_path)
                except Exception as e:
                    # Error reading file - include it to be safe
                    logger.debug(f"Error checking frontmatter: {e}")
                    md_files.append(file_path)
            
            # If not already included based on file timestamps, check frontmatter dates
            if not file_in_date_range and file_path not in md_files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    frontmatter, _ = parse_frontmatter(content)
                    
                    # Check dates in frontmatter
                    for date_field in ['created', 'date', 'creation_date', 'createdAt']:
                        if date_field in frontmatter and frontmatter[date_field]:
                            try:
                                fm_date = parser.parse(str(frontmatter[date_field]))
                                if not isinstance(fm_date, datetime):
                                    fm_date = datetime.combine(fm_date, datetime.min.time())
                                
                                # Check if date is in range
                                if start_boundary.date() <= fm_date.date() <= end_boundary.date():
                                    # Also check processed timestamp if it exists
                                    if 'analyzed' in frontmatter:
                                        try:
                                            analyzed_time = parser.parse(str(frontmatter['analyzed']))
                                            cooldown_period = timedelta(minutes=15)
                                            
                                            # Only include if file metadata date is after analyzed time + cooldown
                                            if fm_date > (analyzed_time + cooldown_period):
                                                logger.debug(f"Frontmatter date after analyzed time + cooldown")
                                                md_files.append(file_path)
                                                break
                                            else:
                                                logger.debug(f"Frontmatter date not after analyzed time + cooldown")
                                                skipped_files += 1
                                        except (ValueError, TypeError):
                                            # Can't parse analyzed time - include it
                                            md_files.append(file_path)
                                    else:
                                        # No analyzed timestamp - include it
                                        logger.debug(f"Frontmatter date in range with no analyzed timestamp")
                                        md_files.append(file_path)
                                        break
                            except (ValueError, TypeError):
                                # Skip unparseable dates
                                pass
                except Exception as e:
                    logger.debug(f"Error checking frontmatter: {e}")
    
    # Log results
    if not md_files:
        logger.warning("No files were found matching the date criteria!")
        if skipped_files > 0:
            logger.warning(f"{skipped_files} files were in date range but skipped (already processed)")
    else:
        logger.info(f"Found {len(md_files)} files for processing")
        for file_path in md_files[:5]:  # Show first 5 files
            logger.info(f"  - {os.path.basename(file_path)}")
        if len(md_files) > 5:
            logger.info(f"  - ... and {len(md_files) - 5} more files")
            
        if skipped_files > 0:
            logger.info(f"Additionally, {skipped_files} files in date range were skipped (already processed)")
    
    return md_files

def clean_note_content(content, analysis_header=None):
    """Remove dataview blocks, template syntax, and AI analysis content from note content"""
    # Remove dataview blocks
    content = re.sub(r'```dataview(?:js)?\n.*?```', '', content, flags=re.DOTALL)
    
    # Remove templating code
    content = re.sub(r'<%.*?%>', '', content, flags=re.DOTALL)
    content = re.sub(r'<<.*?>>', '', content, flags=re.DOTALL)
    content = re.sub(r'\{\{.*?\}\}', '', content, flags=re.DOTALL)
    
    # Remove AI analysis section if processing a daily note and analysis_header is provided
    if analysis_header:
        # Use regex to find and remove the header and all content below it
        pattern = re.escape(analysis_header) + r'.*$'
        content = re.sub(pattern, '', content, flags=re.DOTALL)
    
    return content

def parse_frontmatter(content):
    """Parse YAML frontmatter from markdown content"""
    frontmatter_match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
    
    if frontmatter_match:
        try:
            frontmatter = yaml.safe_load(frontmatter_match.group(1)) or {}
            rest_content = content[frontmatter_match.end():]
            return frontmatter, rest_content
        except yaml.YAMLError:
            logger.warning("Invalid YAML frontmatter")
    
    return {}, content

def update_frontmatter_with_analyzed(content):
    """Update note frontmatter with analyzed timestamp"""
    frontmatter, rest_content = parse_frontmatter(content)
    
    # Add or update analyzed timestamp
    frontmatter['analyzed'] = datetime.now().isoformat()
    
    # Generate new frontmatter with clean formatting
    new_frontmatter = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
    
    # Clean up extra newlines
    if rest_content.strip():
        rest_content = rest_content.lstrip()
        updated_content = f"---\n{new_frontmatter}---\n\n{rest_content}"
    else:
        updated_content = f"---\n{new_frontmatter}---\n"
    
    return updated_content

def is_daily_note(file_path, daily_notes_folder):
    """Check if a file is in the daily notes folder"""
    return os.path.dirname(os.path.abspath(file_path)) == os.path.abspath(daily_notes_folder)

def extract_projects_with_ai(content, prompt, config, provider=None):
    """Extract projects from content using either Ollama or OpenAI"""
    provider = provider or config.get("LLM_PROVIDER", "ollama").lower()
    
    if provider == "openai":
        logger.info(f"Using OpenAI ({config.get('OPENAI_MODEL')}) for project extraction")
        
        try:
            import openai
        except ImportError:
            logger.error("OpenAI package not installed. Run: pip install openai")
            return []
        
        api_key = config.get("OPENAI_API_KEY")
        if not api_key:
            logger.error("No OpenAI API key provided")
            return []
            
        model = config.get("OPENAI_MODEL", "gpt-3.5-turbo")
        max_tokens = config.get("OPENAI_MAX_TOKENS", 4000)
        client = openai.OpenAI(api_key=api_key)
        
        # Setup message payload
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": content}
        ]
        
        # Retry mechanism for rate limits
        max_retries = 5
        base_delay = 20.0
        
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.1,
                )
                
                if response.choices and len(response.choices) > 0:
                    result = response.choices[0].message.content.strip()
                    # Parse the response
                    projects = clean_json_response(result)
                    return projects
                    
            except openai.RateLimitError as e:
                if attempt < max_retries - 1:
                    logger.info(f"Rate limit exceeded, retrying in {base_delay} seconds...")
                    time.sleep(base_delay)
                else:
                    logger.error(f"Maximum retries reached for rate limits")
                    raise e
                    
        logger.error("Failed to get a response from OpenAI")
        return []
        
    else:  # Default to Ollama
        logger.info(f"Using Ollama ({config.get('OLLAMA_MODEL')}) for project extraction")
        
        model = config.get("OLLAMA_MODEL", "gemma3:12b")
        server_address = config.get("OLLAMA_SERVER_ADDRESS", "http://localhost:11434")
        context_window = config.get("OLLAMA_CONTEXT_WINDOW", 32000)
        
        # Build the API payload
        payload = {
            "model": model,
            "prompt": prompt + "\n\n" + content,
            "stream": False,
            "options": {
                "num_ctx": context_window,
                "cache_prompt": False,
                "temperature": 0.1
            }
        }
        
        try:
            response = requests.post(
                f"{server_address}/api/generate",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=180  # Increased timeout for complex prompts
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'response' in result:
                    response_text = result['response'].strip()
                    logger.debug(f"Raw Ollama response: {response_text[:200]}...")  # Log beginning of response
                    
                    # Parse the response
                    projects = clean_json_response(response_text)
                    return projects
            else:
                logger.error(f"API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error calling Ollama API: {e}")
            
        return []

def clean_json_response(response_text):
    """
    Extract and parse JSON from LLM response.
    Now that the prompt specifies proper JSON formatting, this function is simplified
    but still handles code blocks and edge cases.
    """
    if not response_text:
        return []
    
    try:
        # Remove markdown code block markers if present
        cleaned = response_text.strip()
        if cleaned.startswith("```json") or cleaned.startswith("```"):
            # Find the end of the code block
            end_marker = "```"
            if end_marker in cleaned[3:]:
                # Extract content between code block markers
                start_idx = cleaned.find("\n") + 1
                end_idx = cleaned.rfind(end_marker)
                if end_idx > start_idx:
                    cleaned = cleaned[start_idx:end_idx].strip()
                else:
                    cleaned = cleaned[start_idx:].strip()
        
        # Look for JSON array pattern if needed
        if not cleaned.startswith('['):
            array_match = re.search(r'\[\s*\{.+?\}\s*\]', cleaned, re.DOTALL)
            if array_match:
                cleaned = array_match.group(0)
        
        # Parse the JSON
        projects = json.loads(cleaned)
        
        # Validate format - should be an array of objects with title and text properties
        if not isinstance(projects, list):
            logger.warning("LLM response parsed but not a list, returning empty list")
            return []
            
        # Validate each project has required fields
        valid_projects = []
        for project in projects:
            if isinstance(project, dict) and 'title' in project and 'text' in project:
                valid_projects.append(project)
            else:
                logger.warning(f"Skipping invalid project format: {project}")
                
        return valid_projects
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        logger.debug(f"Response text: {response_text[:200]}...")
        return []
    except Exception as e:
        logger.error(f"Error processing LLM response: {e}")
        return []

def generate_analysis_with_ai(projects_json, prompt, config, provider=None):
    """Generate analysis for extracted projects using either Ollama or OpenAI"""
    if not projects_json:
        return ""
    
    # Convert projects JSON to appropriate input format for the analysis prompt
    input_content = json.dumps(projects_json, indent=2)
    
    provider = provider or config.get("LLM_PROVIDER", "ollama").lower()
    
    if provider == "openai":
        logger.info(f"Using OpenAI ({config.get('OPENAI_MODEL')}) for analysis generation")
        
        try:
            import openai
        except ImportError:
            logger.error("OpenAI package not installed. Run: pip install openai")
            return ""
        
        api_key = config.get("OPENAI_API_KEY")
        if not api_key:
            logger.error("No OpenAI API key provided")
            return ""
            
        model = config.get("OPENAI_MODEL", "gpt-3.5-turbo")
        max_tokens = config.get("OPENAI_MAX_TOKENS", 4000)
        client = openai.OpenAI(api_key=api_key)
        
        # Setup message payload
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": input_content}
        ]
        
        # Retry mechanism for rate limits
        max_retries = 5
        base_delay = 20.0
        
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.1,
                )
                
                if response.choices and len(response.choices) > 0:
                    result = response.choices[0].message.content.strip()
                    # If the response starts with a markdown code block, clean it
                    if result.startswith("```") and "```" in result[3:]:
                        result = clean_markdown_response(result)
                    return result
                    
            except openai.RateLimitError as e:
                if attempt < max_retries - 1:
                    logger.info(f"Rate limit exceeded, retrying in {base_delay} seconds...")
                    time.sleep(base_delay)
                else:
                    logger.error(f"Maximum retries reached for rate limits")
                    raise e
                    
        logger.error("Failed to get a response from OpenAI")
        return ""
        
    else:  # Default to Ollama
        logger.info(f"Using Ollama ({config.get('OLLAMA_MODEL')}) for analysis generation")
        
        model = config.get("OLLAMA_MODEL", "gemma3:12b")
        server_address = config.get("OLLAMA_SERVER_ADDRESS", "http://localhost:11434")
        context_window = config.get("OLLAMA_CONTEXT_WINDOW", 32000)
        
        # Build the API payload
        payload = {
            "model": model,
            "prompt": prompt + "\n\n" + input_content,
            "stream": False,
            "options": {
                "num_ctx": context_window,
                "cache_prompt": False
            }
        }
        
        try:
            response = requests.post(
                f"{server_address}/api/generate",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'response' in result:
                    response_text = result['response'].strip()
                    # If the response starts with a markdown code block, clean it
                    if response_text.startswith("```") and "```" in response_text[3:]:
                        response_text = clean_markdown_response(response_text)
                    return response_text
            else:
                logger.error(f"API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error calling Ollama API: {e}")
            
        return ""

def clean_markdown_response(response_text):
    """Clean markdown response by handling code blocks and other formatting issues"""
    if not response_text:
        return ""
        
    try:
        # Check if response starts with a markdown code block
        if response_text.startswith("```"):
            # Handle code blocks with or without language specifier
            first_newline = response_text.find("\n")
            if first_newline > 0:
                # Find the closing code block marker
                end_marker_pos = response_text.rfind("```")
                if end_marker_pos > first_newline:
                    # Extract content between markers
                    content = response_text[first_newline+1:end_marker_pos].strip()
                    
                    # If it looks like markdown, return it
                    if "##" in content or content.startswith("#"):
                        return content
                        
                    # If the content has markdown elements, return it
                    if re.search(r'(\*\*|\*|_|#{1,6}|\[\]|\[.+?\]\(.+?\))', content):
                        return content
        
        # If it didn't start with code blocks or we couldn't process them properly
        # just return the original content since it's likely already in markdown format
        return response_text
        
    except Exception as e:
        logger.error(f"Error cleaning markdown response: {e}")
        # Return original if cleaning fails
        return response_text

def get_or_create_daily_note(config, date=None):
    """Get or create the daily note for the specified date (defaults to today)"""
    if date is None:
        date = datetime.now().date()
    
    daily_notes_folder = config.get("DAILY_NOTES_FOLDER")
    title_format = config.get("DAILY_NOTE_TITLE_FORMAT", "%Y-%m-%d")
    
    # Check for a template file path first
    template_path = config.get("DAILY_NOTE_TEMPLATE_PATH")
    template = ""
    
    if template_path and os.path.exists(template_path):
        try:
            logger.info(f"Loading daily note template from: {template_path}")
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
        except Exception as e:
            logger.error(f"Error loading template file: {e}")
            # Fall back to the inline template
            template = config.get("DAILY_NOTE_TEMPLATE", "")
    else:
        # Use the inline template from config if no template file specified or found
        template = config.get("DAILY_NOTE_TEMPLATE", "")
        if template_path and not os.path.exists(template_path):
            logger.warning(f"Template file not found: {template_path}, using inline template")
    
    # Ensure the daily notes folder exists
    os.makedirs(daily_notes_folder, exist_ok=True)
    
    # Generate filename based on date and title format
    filename = date.strftime(title_format) + ".md"
    file_path = os.path.join(daily_notes_folder, filename)
    
    # Check if the file already exists
    if os.path.exists(file_path):
        logger.info(f"Daily note already exists: {file_path}")
        return file_path
    
    # Replace template variables with actual date
    date_str = date.strftime("%Y-%m-%d")
    date_formatted = date.strftime("%A, %B %d, %Y")  # Example: Monday, January 1, 2024
    
    # Handle various date format placeholders in the template
    template = template.replace("{{date}}", date_str)
    template = template.replace("{{date:YYYY-MM-DD}}", date_str)
    template = template.replace("{{date:dddd, MMMM D, YYYY}}", date_formatted)
    
    # Create the daily note with template
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(template)
        logger.info(f"Created new daily note: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Error creating daily note: {e}")
        return None

def append_analysis_to_daily_note(daily_note_path, analysis, analysis_header):
    """Append analysis to the daily note under the specified header"""
    if not daily_note_path or not analysis:
        return False
    
    try:
        # Read existing content
        with open(daily_note_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if the analysis header already exists
        if analysis_header in content:
            # Replace existing section
            pattern = re.escape(analysis_header) + r'.*?(?=\n#|\Z)'
            replacement = f"{analysis_header}\n\n{analysis}"
            updated_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        else:
            # Append to the end with proper spacing
            if content and not content.endswith('\n\n'):
                if content.endswith('\n'):
                    updated_content = f"{content}\n{analysis_header}\n\n{analysis}"
                else:
                    updated_content = f"{content}\n\n{analysis_header}\n\n{analysis}"
            else:
                updated_content = f"{content}{analysis_header}\n\n{analysis}"
        
        # Write updated content
        with open(daily_note_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
            
        logger.info(f"Appended analysis to daily note: {daily_note_path}")
        return True
    except Exception as e:
        logger.error(f"Error appending analysis to daily note: {e}")
        return False

def main():
    """Main function to process markdown files and generate/append analysis"""
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Generate project analysis for Obsidian notes')
    parser.add_argument('--date', help='Override date to check (YYYY-MM-DD format)')
    parser.add_argument('--debug', action='store_true', help='Enable detailed debug logging')
    parser.add_argument('--input', help='Override input folder')
    parser.add_argument('--exclude', action='append', help='Override exclude folders (can be used multiple times)')
    parser.add_argument('--daily', help='Override daily notes folder')
    parser.add_argument('--model', help='Override model name')
    parser.add_argument('--server', help='Override Ollama server address')
    parser.add_argument('--provider', choices=['ollama', 'openai'], help='LLM provider (ollama or openai)')
    parser.add_argument('--api-key', help='Override OpenAI API key')
    parser.add_argument('--delay', type=float, default=0, help='Delay between processing files (seconds)')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 
                      default='INFO', help='Set logging level')
    args = parser.parse_args()
    
    # Set log level
    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(getattr(logging, args.log_level))
    
    logger.info("=== Starting generate_analysis.py ===")
    
    # Load and override configuration
    config = load_config()
    if args.input: config["INPUT_FOLDER"] = args.input
    if args.exclude: config["EXCLUDE_FOLDERS"] = args.exclude
    if args.daily: config["DAILY_NOTES_FOLDER"] = args.daily
    if args.provider: config["LLM_PROVIDER"] = args.provider
    if args.api_key: config["OPENAI_API_KEY"] = args.api_key
    if args.model:
        if config.get("LLM_PROVIDER") == "openai" or args.provider == "openai":
            config["OPENAI_MODEL"] = args.model
        else:
            config["OLLAMA_MODEL"] = args.model
    if args.server: config["OLLAMA_SERVER_ADDRESS"] = args.server
    
    # Extract common config values
    input_folder = config["INPUT_FOLDER"]
    exclude_folders = config["EXCLUDE_FOLDERS"]
    daily_notes_folder = config["DAILY_NOTES_FOLDER"]
    llm_provider = config["LLM_PROVIDER"]
    analysis_header = config["ANALYSIS_HEADER"]
    
    # Get prompt files
    script_dir = os.path.dirname(os.path.abspath(__file__))
    extract_prompt_path = os.path.join(script_dir, "extract_projects.md")
    analysis_prompt_path = os.path.join(script_dir, "generate_analysis.md")
    
    # Log basic configuration
    logger.info(f"Configuration: Input={input_folder}, Provider={llm_provider}")
    logger.info(f"Daily notes folder: {daily_notes_folder}")
    if llm_provider.lower() == "openai":
        if args.delay > 0:
            logger.info(f"Using OpenAI with {args.delay}s delay between files")
        else:
            logger.info("Using OpenAI with no delay (add --delay 5 to avoid rate limits)")
    
    # Verify prompt files exist
    for path, name in [(extract_prompt_path, "project extraction"), (analysis_prompt_path, "project analysis")]:
        if not os.path.exists(path):
            logger.error(f"Prompt file for {name} not found: {path}")
            return
    
    # Load prompt files
    try:
        with open(extract_prompt_path, 'r') as f:
            extract_prompt = f.read()
        with open(analysis_prompt_path, 'r') as f:
            analysis_prompt = f.read()
    except Exception as e:
        logger.error(f"Error reading prompt files: {e}")
        return
    
    # Get time boundaries and find matching files
    start_boundary, end_boundary = get_previous_day_boundaries(args.date)
    try:
        md_files = find_md_files_from_previous_day(input_folder, exclude_folders, start_boundary, end_boundary)
    except Exception as e:
        logger.error(f"Error finding files: {e}")
        return
    
    if not md_files:
        logger.info("No files found matching the date criteria. Exiting.")
        return
    
    # Process each file
    all_projects = []
    files_processed = 0
    files_with_errors = 0
    total_files = len(md_files)
    
    try:
        for index, file_path in enumerate(md_files):
            filename = os.path.basename(file_path)
            progress = f"[{index+1}/{total_files}]"
            logger.info(f"{progress} Processing: {filename}")
            
            try:
                # Read and clean content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # If this is a daily note, clean it specially to remove any AI analysis from the previous run
                if is_daily_note(file_path, daily_notes_folder):
                    clean_content = clean_note_content(content, analysis_header)
                    logger.info(f"{progress} Processing daily note, removed any existing AI analysis")
                else:
                    clean_content = clean_note_content(content)
                
                # Extract projects
                logger.info(f"{progress} Extracting projects from {filename}")
                projects = extract_projects_with_ai(clean_content, extract_prompt, config)
                
                if not projects:
                    logger.info(f"{progress} No actionable projects found in {filename}")
                else:
                    logger.info(f"{progress} Found {len(projects)} actionable projects in {filename}")
                    all_projects.extend(projects)
                
                # Update analyzed timestamp in frontmatter
                updated_content = update_frontmatter_with_analyzed(content)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                
                files_processed += 1
                
                # Add delay between files if specified
                if args.delay > 0 and llm_provider.lower() == "openai" and index < total_files - 1:
                    logger.info(f"Waiting {args.delay}s before next file...")
                    time.sleep(args.delay)
                    
            except Exception as e:
                logger.error(f"{progress} Error processing {filename}: {e}")
                files_with_errors += 1
        
        # Generate analysis for all extracted projects
        if all_projects:
            logger.info(f"Generating analysis for {len(all_projects)} extracted projects")
            analysis = generate_analysis_with_ai(all_projects, analysis_prompt, config)
            
            if analysis:
                # Get or create today's daily note
                today = datetime.now().date()
                daily_note_path = get_or_create_daily_note(config, today)
                
                if daily_note_path:
                    # Append analysis to daily note
                    success = append_analysis_to_daily_note(daily_note_path, analysis, analysis_header)
                    if success:
                        logger.info(f"Successfully appended analysis to daily note for {today}")
                    else:
                        logger.error(f"Failed to append analysis to daily note for {today}")
                else:
                    logger.error(f"Failed to get or create daily note for {today}")
            else:
                logger.warning("No analysis was generated from the extracted projects")
        else:
            logger.info("No actionable projects were found in any of the processed files")
                
    except KeyboardInterrupt:
        logger.warning("Process interrupted by user")
    
    # Log summary
    logger.info(f"=== Summary: {files_processed}/{total_files} files processed, {len(all_projects)} projects found, {files_with_errors} errors ===")
    if llm_provider.lower() == "openai" and args.delay == 0 and files_with_errors > 0:
        logger.info("Tip: Use --delay 5 to avoid OpenAI API rate limits")

if __name__ == "__main__":
    # Set up logging
    script_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(script_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, f"generate_analysis_{datetime.now().strftime('%Y-%m-%d')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger(__name__)
    logger.info(f"Logging to: {log_file}")
    
    try:
        main()
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        sys.exit(1)