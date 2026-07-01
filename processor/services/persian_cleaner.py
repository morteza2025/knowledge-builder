import re


ARABIC_TO_PERSIAN_MAP = {
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "ۀ": "ه",
    "ة": "ه",
    "ؤ": "و",
    "إ": "ا",
    "أ": "ا",
    "ٱ": "ا",
}


def normalize_persian_chars(text: str) -> str:
    for old, new in ARABIC_TO_PERSIAN_MAP.items():
        text = text.replace(old, new)
    return text


def normalize_spaces(text: str) -> str:
    text = text.replace("\r", "\n")
    text = text.replace("\t", " ")
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def remove_noise_lines(text: str) -> str:
    lines = [line.strip() for line in text.split("\n")]
    cleaned = []

    for line in lines:
        if not line:
            continue

        # حذف خط‌های خیلی بی‌ارزش
        if len(line) <= 1:
            continue

        # حذف خط‌هایی که فقط عدد یا علامت‌اند
        if re.fullmatch(r"[\d\s\-\–\—_.:|/\\]+", line):
            continue

        cleaned.append(line)

    return "\n".join(cleaned)


def fix_common_pdf_line_breaks(text: str) -> str:
    """
    این تابع خیلی محتاط عمل می‌کند.
    فعلاً جمله‌ها را بی‌خطرتر مرتب می‌کند، ولی متن کتاب را دستکاری سنگین نمی‌کند.
    """
    lines = text.split("\n")
    result = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        result.append(line)

    return "\n".join(result)


def clean_persian_text(text: str) -> str:
    if not text:
        return ""

    text = normalize_persian_chars(text)
    text = normalize_spaces(text)
    text = remove_noise_lines(text)
    text = fix_common_pdf_line_breaks(text)
    text = normalize_spaces(text)

    return text.strip()