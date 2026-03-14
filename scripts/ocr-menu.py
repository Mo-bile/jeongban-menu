#!/usr/bin/env python3
"""
정반식당 주간 메뉴표 이미지에서 오늘의 메뉴를 OCR로 추출합니다.

사용법:
  python scripts/ocr-menu.py <image_path_or_url> [weekday]
  weekday: 0=월, 1=화, 2=수, 3=목, 4=금 (생략 시 오늘 요일 자동 감지)

출력: JSON (stdout)
  성공: {"success": true, "weekday": "월", "menu": [...], "is_holiday": false}
  공휴일: {"success": true, "weekday": "월", "menu": [], "is_holiday": true}
  실패: {"success": false, "error": "..."}
"""

import sys
import json
import os
import tempfile
import urllib.request
from datetime import datetime
from PIL import Image

EXCLUDED_ROW_KEYWORDS = ["프레시 박스", "헬시밀 박스", "프레시박스", "헬시밀박스", "프레시", "프레쉬", "헬시밀"]

# 구분 열에서 이 키워드가 나오면 해당 y 이후를 제외 (프레쉬/헬시밀 박스 시작점)
EXCLUDED_SECTION_KEYWORDS = ["프레시", "프레쉬", "헬시밀"]
WEEKDAY_NAMES = ["월", "화", "수", "목", "금"]

# 하단 안내문구 시작 키워드 (이후 텍스트 전부 제거)
FOOTER_KEYWORDS = ["문의사항", "* 문의", "* 메뉴", "* 해당", "* 특정", "※", "* 문"]

# 노이즈 텍스트 패턴 (정규식)
NOISE_PATTERNS = [
    r"^[-–—=_*·•<>/]+$",    # 대시/구분선/기호만 있는 텍스트
    r"^<[^>]+>",             # HTML 태그
    r"^[^\uAC00-\uD7A3a-zA-Z0-9]+$",  # 한글/영숫자 없는 기호만
]

# 공휴일 이미지에 자주 등장하는 키워드 (메뉴 텍스트와 구분되는 명확한 키워드만)
HOLIDAY_IMAGE_KEYWORDS = [
    "Happy New Year",
    "새해 복 많이",
    "새해복 많이",
    "명절 연휴",
    "설날 연휴",
    "추석 연휴",
    "행복하세요!",
    "붉은 말의 해",
    "병오년 행복",
]

# 공휴일 판단: 유의미한 메뉴 텍스트 수가 이 미만이면 공휴일로 간주
HOLIDAY_TEXT_THRESHOLD = 3


def download_image(source: str) -> Image.Image:
    """URL 또는 로컬 경로에서 이미지를 로드합니다."""
    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(source) as resp:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(resp.read())
                tmp_path = f.name
        try:
            img = Image.open(tmp_path).convert("RGB")
        finally:
            os.unlink(tmp_path)
        return img
    return Image.open(source).convert("RGB")


def run_ocr(image: Image.Image):
    """Surya로 텍스트 라인 검출 + 인식을 수행합니다."""
    from surya.detection import DetectionPredictor
    from surya.recognition import RecognitionPredictor
    from surya.foundation import FoundationPredictor

    det_predictor = DetectionPredictor()
    foundation = FoundationPredictor()
    rec_predictor = RecognitionPredictor(foundation)

    ocr_results = rec_predictor([image], det_predictor=det_predictor)
    return ocr_results[0]


def run_table_rec(image: Image.Image):
    """Surya로 표 구조(행/열/셀)를 인식합니다."""
    from surya.table_rec import TableRecPredictor

    predictor = TableRecPredictor()
    results = predictor([image])
    return results[0]


def bbox_center_x(bbox):
    return (bbox[0] + bbox[2]) / 2


def bbox_center_y(bbox):
    return (bbox[1] + bbox[3]) / 2


def overlap_ratio(a, b):
    """두 bbox의 x축 겹침 비율 (a 기준)."""
    ax1, _, ax2, _ = a
    bx1, _, bx2, _ = b
    inter = max(0, min(ax2, bx2) - max(ax1, bx1))
    width_a = ax2 - ax1
    if width_a == 0:
        return 0
    return inter / width_a


def assign_text_to_columns(text_lines, col_bboxes, img_width):
    """각 텍스트 라인을 컬럼에 배정합니다."""
    col_texts = [[] for _ in col_bboxes]

    for line in text_lines:
        text = line.text.strip()
        if not text:
            continue
        lbbox = line.bbox
        best_col = -1
        best_ratio = 0.0
        for ci, cbbox in enumerate(col_bboxes):
            r = overlap_ratio(lbbox, cbbox)
            if r > best_ratio:
                best_ratio = r
                best_col = ci
        if best_col >= 0 and best_ratio > 0.3:
            col_texts[best_col].append((bbox_center_y(lbbox), text))

    # y 좌표 기준으로 정렬
    for ci in range(len(col_texts)):
        col_texts[ci].sort(key=lambda x: x[0])

    return col_texts


def is_excluded_row_start(text: str) -> bool:
    """프레시 박스, 헬시밀 박스 등 제외 시작 키워드 확인."""
    for kw in EXCLUDED_ROW_KEYWORDS:
        if kw in text:
            return True
    return False


def is_footer(text: str) -> bool:
    """하단 안내문구 여부 확인."""
    for kw in FOOTER_KEYWORDS:
        if text.startswith(kw):
            return True
    # '* 문의사항', '* 메뉴' 등 * 로 시작하는 안내문
    if text.startswith("*") and any(kw in text for kw in ["문의", "메뉴", "해당", "특정", "알러지"]):
        return True
    return False


def is_header_noise(text: str) -> bool:
    """날짜, 요일명, 브랜드명, 노이즈 텍스트 여부 확인."""
    import re
    t = text.strip()
    # '02월 09일', '월', '화' 등 날짜/요일 단독 텍스트
    if re.fullmatch(r"\d{2}월\s*\d{2}일", t):
        return True
    if t in ["월", "화", "수", "목", "금", "토", "일", "호"]:
        return True
    # 브랜드명 노이즈 (부분 포함 여부 확인)
    BRAND_KEYWORDS = ["正바를", "주간메뉴표", "[ 중식 ]", "[중식]"]
    if any(kw in t for kw in BRAND_KEYWORDS):
        return True
    if re.match(r"\[?\s*중식\s*\]?\s*\d+:\d+", t):
        return True
    # 숫자만 단독 (1~3자리)
    if re.fullmatch(r"\d{1,3}", t):
        return True
    # 노이즈 패턴
    for pattern in NOISE_PATTERNS:
        if re.search(pattern, t):
            return True
    return False


def find_excluded_y_threshold(text_lines, col_bboxes):
    """
    구분 열(col[0])에서 PLUS / 프레시 / 헬시밀 등 섹션 구분 키워드를 찾아
    해당 행 시작 y 좌표를 반환합니다. 이 y 이상의 텍스트는 모든 열에서 제외합니다.

    OCR이 "프레쉬" + "박스" 처럼 단어를 분리해서 인식하는 경우에도 동작합니다.
    PLUS 행의 y 좌표를 찾아 그 이후(프레시박스, 헬시밀박스)를 모두 제외합니다.
    """
    if not col_bboxes:
        return float("inf")

    label_col_bbox = col_bboxes[0]
    threshold = float("inf")

    for line in text_lines:
        text = line.text.strip()
        if not text:
            continue
        matched = any(kw in text for kw in EXCLUDED_SECTION_KEYWORDS)
        if matched:
            r = overlap_ratio(line.bbox, label_col_bbox)
            if r > 0.2:
                y = line.bbox[1]  # 행 상단 y 좌표
                if y < threshold:
                    threshold = y

    return threshold


def extract_menu_for_weekday(text_lines, col_bboxes, table_result, weekday_idx: int, img_width: int):
    """
    지정된 요일(컬럼 인덱스)의 메뉴 텍스트를 추출합니다.

    표 구조: 0번 컬럼 = '구분' 레이블, 1~5번 컬럼 = 월~금
    weekday_idx: 0=월, 1=화, 2=수, 3=목, 4=금
    """
    # 구분 열에서 제외 행 y 기준 먼저 계산
    excluded_y = find_excluded_y_threshold(text_lines, col_bboxes)

    col_texts = assign_text_to_columns(text_lines, col_bboxes, img_width)

    # 컬럼 수가 6개 미만이면 구분 컬럼 없이 1~5 직접 매핑
    target_col_idx = weekday_idx + 1 if len(col_bboxes) >= 6 else weekday_idx

    if target_col_idx >= len(col_texts):
        return [], False

    # y 기준 이하 텍스트 사전 제거
    raw_texts = [t for y, t in col_texts[target_col_idx] if y < excluded_y]

    # 필터링: 헤더 노이즈, 하단 안내문구, 중복 제거
    menu_texts = []
    seen = set()
    for text in raw_texts:
        if is_footer(text):
            break
        if is_excluded_row_start(text):
            break
        if is_header_noise(text):
            continue
        if text in seen:
            continue
        seen.add(text)
        menu_texts.append(text)

    # 공휴일 감지: 유의미한 메뉴 텍스트 수가 임계값 미만
    is_holiday = len(menu_texts) < HOLIDAY_TEXT_THRESHOLD

    return menu_texts, is_holiday


def sort_col_bboxes(table_result):
    """TableRecPredictor 결과에서 컬럼 bbox를 x 순서로 정렬하여 반환합니다."""
    if not hasattr(table_result, "cols") or not table_result.cols:
        return []
    cols = sorted(table_result.cols, key=lambda c: c.bbox[0])
    return [c.bbox for c in cols]


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "이미지 경로 또는 URL을 인자로 전달하세요."}))
        sys.exit(1)

    source = sys.argv[1]

    # 요일 결정
    if len(sys.argv) >= 3:
        try:
            weekday_idx = int(sys.argv[2])
        except ValueError:
            weekday_idx = datetime.today().weekday()
    else:
        weekday_idx = datetime.today().weekday()

    # 평일(0~4)이 아니면 운영 안 함
    if weekday_idx > 4:
        print(json.dumps({
            "success": True,
            "weekday": WEEKDAY_NAMES[0],
            "menu": [],
            "is_holiday": True,
            "reason": "주말에는 식당을 운영하지 않습니다."
        }))
        return

    weekday_name = WEEKDAY_NAMES[weekday_idx]

    try:
        image = download_image(source)
    except Exception as e:
        print(json.dumps({"success": False, "error": f"이미지 로드 실패: {e}"}))
        sys.exit(1)

    try:
        table_result = run_table_rec(image)
        col_bboxes = sort_col_bboxes(table_result)
    except Exception as e:
        print(json.dumps({"success": False, "error": f"표 인식 실패: {e}"}))
        sys.exit(1)

    try:
        ocr_result = run_ocr(image)
        text_lines = ocr_result.text_lines
    except Exception as e:
        print(json.dumps({"success": False, "error": f"OCR 실패: {e}"}))
        sys.exit(1)

    menu_texts, is_holiday = extract_menu_for_weekday(
        text_lines, col_bboxes, table_result, weekday_idx, image.width
    )

    # 공휴일 이미지 키워드 감지 (추가 체크)
    if not is_holiday:
        combined = " ".join(menu_texts)
        for kw in HOLIDAY_IMAGE_KEYWORDS:
            if kw in combined:
                is_holiday = True
                menu_texts = []
                break

    if is_holiday:
        print(json.dumps({
            "success": True,
            "weekday": weekday_name,
            "menu": [],
            "is_holiday": True,
            "reason": f"공휴일로 인해 식당을 운영하지 않습니다."
        }, ensure_ascii=False))
    else:
        print(json.dumps({
            "success": True,
            "weekday": weekday_name,
            "menu": menu_texts,
            "is_holiday": False
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
