import os
from dotenv import load_dotenv

load_dotenv()
import shutil
from pathlib import Path
import yaml

# Category mapping for folder resolution
CATEGORY_MAP = {
    "get": "10. GCCS process/11. Get",
    "connect": "10. GCCS process/12. Connect",
    "create": "10. GCCS process/13. Create",
    "share": "10. GCCS process/14. Share",
    "projects": "20. Projects",
    "assets": "50. Assets",
    "outputs": "60. Outputs",
    "references": "80. References",
    "settings": "90. Settings",
}

# Obsidian Inbox directory
INBOX_DIR = Path(os.getenv("BASE_PATH")) / "00. Inbox"


def extract_category(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if lines[0].strip() != "---":
                return None  # Not a frontmatter file
            frontmatter = []
            for line in lines[1:]:
                if line.strip() == "---":
                    break
                frontmatter.append(line)
            data = yaml.safe_load("".join(frontmatter))
            category = data.get("category", None)
            return category
    except Exception as e:
        print(f"[오류] {filepath.name}에서 카테고리 추출 실패: {e}")
        return None


def move_file_to_category(filepath, category):
    parent_dir = INBOX_DIR.parent
    category_path = CATEGORY_MAP.get(category.lower(), category)

    # Handle nested subcategories (e.g., get/ai)
    parts = category.split("/")
    base_key = parts[0].lower()
    sub_parts = parts[1:] if len(parts) > 1 else []

    mapped_base = CATEGORY_MAP.get(base_key, base_key)
    mapped_parts = mapped_base.split("/") + sub_parts

    # 실제 경로에서 대소문자 무시한 전체 경로 매핑
    full_match = []
    current_dir = INBOX_DIR.parent
    if not current_dir.exists():
        print(f"[경고] 폴더가 존재하지 않아 생성됨: {current_dir}")
        current_dir.mkdir(parents=True, exist_ok=True)
    for part in mapped_parts:
        if not current_dir.exists():
            print(f"[경고] 경로 없음: {current_dir}")
            return
        match = next(
            (
                p.name
                for p in current_dir.iterdir()
                if p.is_dir() and p.name.lower() == part.lower()
            ),
            None,
        )
        if match:
            full_match.append(match)
            current_dir = current_dir / match
        else:
            full_match.append(part)
            current_dir = current_dir / part
    dest_folder = INBOX_DIR.parent.joinpath(*full_match)
    dest_folder.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(filepath), dest_folder / filepath.name)
        print(f"[이동 완료] {filepath.name} → {dest_folder}")
    except Exception as e:
        print(f"[이동 실패] {filepath.name}: {e}")
    return


def organize_files():
    md_files = list(INBOX_DIR.glob("*.md"))
    for md_file in md_files:
        category = extract_category(md_file)
        if category:
            move_file_to_category(md_file, category)


if __name__ == "__main__":
    organize_files()
