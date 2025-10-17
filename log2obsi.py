import os
from dotenv import load_dotenv

load_dotenv()
import datetime
import re
import sys
from pathlib import Path
import argparse

TAG_PATTERN = re.compile(r"^-?\s*#\w+(?:/\w+)?\s*$")

# Obsidian base path (can be configured via .env)
BASE_PATH = Path(
    os.getenv(
        "BASE_PATH",
        Path.home()
        / "Library/Mobile Documents/com~apple~CloudDocs/ami0bsidian/ami0bsidian",
    )
)
VAULT_PATH = BASE_PATH
JOURNAL_PATH = VAULT_PATH / "journals"

# Last run file path (can be configured via .env)
LAST_RUN_FILE = Path(
    os.getenv(
        "LAST_RUN_FILE", Path(__file__).resolve().parent / "log2obsi_last_run.txt"
    )
)


def parse_args():
    parser = argparse.ArgumentParser(description="log2obsi runner")
    parser.add_argument(
        "--debug", action="store_true", help="Run in debug mode (process last 1 month)"
    )
    parser.add_argument(
        "--date", type=str, help="Run for a specific date (format: YYYY-MM-DD)"
    )
    return parser.parse_args()


args = parse_args()
DEBUG_MODE = args.debug

if getattr(args, "date", None):
    try:
        specific_date = datetime.datetime.strptime(args.date, "%Y-%m-%d")
        START_DATE = specific_date
        END_DATE = specific_date + datetime.timedelta(days=1)
        print(f"📆 Running for specific date: {args.date}")
    except ValueError:
        print("❌ Invalid date format. Use YYYY-MM-DD.")
        sys.exit(1)
elif DEBUG_MODE:
    START_DATE = datetime.datetime.now() - datetime.timedelta(days=30)
    END_DATE = datetime.datetime.now()
    print("🔧 DEBUG_MODE active: processing last 1 month")
else:
    if LAST_RUN_FILE.exists():
        last_run_date = datetime.datetime.strptime(
            LAST_RUN_FILE.read_text().strip(), "%Y-%m-%d"
        )
        START_DATE = last_run_date + datetime.timedelta(days=1)
    else:
        START_DATE = datetime.datetime.now() - datetime.timedelta(days=2)
    END_DATE = datetime.datetime.now()


def get_indent(line: str) -> int:
    expanded = line.expandtabs(4)
    leading_spaces = len(expanded) - len(expanded.lstrip())
    return leading_spaces // 4


def extract_blocks(filepath):
    lines = Path(filepath).read_text(encoding="utf-8").splitlines()
    lines = [line for line in lines if not line.strip().startswith("collapsed::")]
    blocks = []
    i = 0

    all_blocks = []
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*-\s+", line):
            start_idx = i
            parent_indent = get_indent(line)
            block = [line]
            i += 1
            while i < len(lines):
                next_line = lines[i]
                next_indent = get_indent(next_line)
                if re.match(r"^\s*-\s+", next_line) and next_indent <= parent_indent:
                    break
                block.append(next_line)
                i += 1
            all_blocks.append((start_idx, parent_indent, block))
        else:
            i += 1

    tag_blocks_indices = []
    for idx, (start, indent, blk) in enumerate(all_blocks):
        for line in blk:
            line_stripped = line.strip()
            if line_stripped.startswith("#"):
                pass
            if TAG_PATTERN.fullmatch(line_stripped):
                tag_blocks_indices.append(idx)
                break

    collected_blocks = set()
    final_results = []

    for tag_idx in tag_blocks_indices:
        tag_start, tag_indent, tag_block = all_blocks[tag_idx]
        collected_blocks.add(tag_idx)

        parent_idx = None
        for j in range(tag_idx - 1, -1, -1):
            if all_blocks[j][1] < tag_indent:
                parent_idx = j
                break

        children = []
        for m in range(tag_idx + 1, len(all_blocks)):
            child_start, child_indent, child_blk = all_blocks[m]
            if child_indent > tag_indent:
                children.append(m)
            elif child_indent <= tag_indent:
                break

        if parent_idx is not None:
            collected_blocks.add(parent_idx)
        collected_blocks.update(children)

        # Extract the tag line and title line
        title_line = (
            all_blocks[parent_idx][2][0] if parent_idx is not None else tag_block[0]
        )
        tag_line = next(
            (line for line in tag_block if TAG_PATTERN.fullmatch(line.strip())), None
        )

        # Combine parent block and children blocks into one string
        combined_lines = []
        if parent_idx is not None:
            combined_lines.extend(all_blocks[parent_idx][2])
        else:
            combined_lines.extend(tag_block)
        for child_idx in children:
            combined_lines.extend(all_blocks[child_idx][2])
        full_block = "\n".join(combined_lines)

        if tag_line:
            final_results.append((title_line.strip(), tag_line.strip(), full_block))

    return final_results


def get_output_dir_from_tag(tag: str) -> Path:
    tag_clean = tag.strip()
    tag_key_match = re.search(r"#(\w+(?:/\w+)?)", tag_clean)
    if not tag_key_match:
        return None
    tag_key = tag_key_match.group(1)
    parts = tag_key.split("/")
    prefix = parts[0].lower()
    # Normalize prefix and check against known folder keywords
    top_keywords = [
        "project",
        "get",
        "connect",
        "create",
        "output",
        "ref",
        "setting",
        "inbox",
    ]
    # Check for exact matches only
    if tag_key.lower() in top_keywords and "/" not in tag_key:
        project_dir = ""
    elif len(parts) > 1:
        project_dir = parts[1]
    else:
        project_dir = "misc"

    folder_map = {
        "project": f"20. Projects/{project_dir}".rstrip("/"),
        "get": f"10. GCCS process/11. Get/{project_dir}".rstrip("/"),
        "connect": f"10. GCCS process/12. Connect/{project_dir}".rstrip("/"),
        "create": f"10. GCCS process/13. Create/{project_dir}".rstrip("/"),
        "output": f"60. Outputs/{project_dir}".rstrip("/"),
        "ref": f"80. References/{project_dir}".rstrip("/"),
        "setting": f"90. Settings/{project_dir}".rstrip("/"),
        "inbox": f"00. Inbox/{project_dir}".rstrip("/"),
    }

    folder = folder_map.get(prefix)
    if folder:
        return VAULT_PATH / folder
    return None


def write_block_to_file(title: str, tag: str, block_content: str, original_path: Path):
    tag_clean = tag.strip()
    tag_match = re.search(r"#(\w+(?:/\w+)?)", tag_clean)
    if not tag_match:
        print(f"❌ Could not extract valid tag from line: {tag}")
        return
    tag_key = tag_match.group(1)
    tag_key = tag_key.lower()

    # Remove leading date and tag slug from title for YAML
    clean_title = re.sub(r"^\d{4}[_-]\d{2}[_-]\d{2}[_-]\s*#\S+\s*", "", title).strip()
    clean_title = re.sub(r"^[\W_]+", "", clean_title)
    clean_filename = re.sub(r'[\\/*?:"<>|]', "", clean_title).strip()
    clean_filename = re.sub(r"__+", "_", clean_filename)
    # filename = f"{clean_filename}.md"
    output_dir = get_output_dir_from_tag(tag)
    if output_dir is None:
        print(f"❌ Unrecognized tag: {tag}")
        return

    date_str = original_path.stem.replace("_", "-")
    parts = tag_key.split("/")

    # Remove leading hyphen and space if present
    clean_title = re.sub(r"^-+\s*", "", clean_title).strip()

    output_dir.mkdir(parents=True, exist_ok=True)
    base_filename = clean_filename
    output_path = output_dir / f"{base_filename}.md"

    if not getattr(args, "date", None):
        count = 1
        while output_path.exists():
            output_path = output_dir / f"{base_filename} ({count}).md"
            count += 1
        if count > 1:
            print(f"⚠️ Duplicate detected. Saved as: {output_path.name}")

    main_tag = parts[0] if len(parts) > 0 else "unknown"
    contents = f"""---
title: "{clean_title}"
date: {date_str}
category: {main_tag}
tags:
  - "{tag_key}"
---
{block_content.strip()}
"""
    contents = re.sub(
        r"^collapsed::\s*(true|false)\s*$", "", contents, flags=re.MULTILINE
    )

    # Copy images and adjust paths (copy to shared assets folder, use assets/xxx format)
    image_pattern = re.compile(r"!\[.*?\]\((\.\./assets/([^)\"']+))\)")
    matches = image_pattern.findall(block_content)

    for full_match, img_name in matches:
        contents = contents.replace(full_match, f"assets/{img_name}")

    # ✅ write contents AFTER image replacement
    output_path.write_text(contents, encoding="utf-8")
    print(f"✅ Saved: {output_path}")

    with open(BASE_PATH / "log2obsi_run_log.txt", "a", encoding="utf-8") as log_file:
        log_file.write(
            f"{datetime.datetime.now().isoformat()} - Saved: {output_path}\n"
        )


def main():
    def extract_date_from_filename(file_path):
        try:
            return datetime.datetime.strptime(file_path.stem, "%Y_%m_%d")
        except ValueError:
            return None

    md_files = [
        f
        for f in JOURNAL_PATH.glob("*.md")
        if f.is_file()
        and not any(p in str(f) for p in [".logseq", "logseq"])
        and extract_date_from_filename(f) is not None
        and extract_date_from_filename(f) >= START_DATE
        and extract_date_from_filename(f) < END_DATE
    ]

    if not md_files:
        print("⚠️ No recent journal files to process.")
        if not DEBUG_MODE and not getattr(args, "date", None):
            now_date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            print(f"📝 Last run date will be saved as: {now_date_str}")
            try:
                LAST_RUN_FILE.write_text(now_date_str)
            except Exception as e:
                print(f"❌ Failed to write last run file: {e}")
        sys.exit(0)

    print(f"📁 Found {len(md_files)} journal files to process.\n")

    for filepath in md_files:
        print(f"📂 Processing file: {filepath.name}")
        results = extract_blocks(filepath)
        for title, tag, block in results:
            print(f"[TITLE] {title}")
            print(f"[TAG]   {tag}")
            write_block_to_file(title, tag, block, filepath)

    if not DEBUG_MODE and not getattr(args, "date", None):
        now_date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        print(f"📝 Updating last run date to: {now_date_str}")
        try:
            LAST_RUN_FILE.write_text(now_date_str)
        except Exception as e:
            print(f"❌ Failed to write last run file: {e}")


if __name__ == "__main__":
    main()
