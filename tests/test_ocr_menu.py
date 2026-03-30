#!/usr/bin/env python3
"""
ocr-menu.py 통합 테스트.

환경변수:
  SKIP_OCR_MODEL=1   Surya 모델 로딩 없이 헬퍼 함수(노이즈 필터 등) 단위 테스트만 실행
  TEST_IMAGE_PATH    기본 fixture 이미지 경로 덮어쓰기

실행:
  # 단위 테스트만 (모델 불필요)
  SKIP_OCR_MODEL=1 python -m pytest tests/test_ocr_menu.py -v

  # OCR 통합 테스트 포함 (Surya 모델 필요, 수 분 소요)
  python -m pytest tests/test_ocr_menu.py -v
"""

import json
import os
import sys
import subprocess
from pathlib import Path

import pytest

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore

# 프로젝트 루트를 sys.path에 추가
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

SKIP_OCR = os.environ.get("SKIP_OCR_MODEL") == "1"

FIXTURE_IMAGE = Path(
    os.environ.get(
        "TEST_IMAGE_PATH",
        str(REPO_ROOT / "tests/fixtures/menu-2026-03-30.png"),
    )
)

# 새 메뉴판(2026-03-30 주차)에서 기대하는 특선 메뉴
EXPECTED_SPECIALS = {
    0: "미트소스 스파게티",   # 월
    1: "버섯 곤드레모듬나물밥",  # 화
    2: "데리야끼 베이비크랩강정",  # 수
    3: "콩나물불고기",          # 목
    4: "솔방울 오징어초무침",    # 금
}

# 각 요일별로 반드시 포함돼야 하는 메뉴 아이템 (대표 1개)
EXPECTED_MENU_ITEMS = {
    0: "추가밥",       # 월
    1: "콩나물된장국",  # 화
    2: "쌀밥",         # 수
    3: "쌀밥",         # 목
    4: "쌀밥",         # 금
}


# ──────────────────────────────────────────────
# 단위 테스트 (모델 불필요)
# ──────────────────────────────────────────────

def import_ocr_helpers():
    """ocr-menu 모듈에서 헬퍼 함수와 상수를 임포트합니다."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ocr_menu", REPO_ROOT / "scripts" / "ocr-menu.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def ocr_mod():
    return import_ocr_helpers()


class TestNoiseFilter:
    def test_date_filtered(self, ocr_mod):
        assert ocr_mod.is_header_noise("03월 30일")
        assert ocr_mod.is_header_noise("12월 01일")

    def test_weekday_filtered(self, ocr_mod):
        for wd in ["월", "화", "수", "목", "금"]:
            assert ocr_mod.is_header_noise(wd), f"{wd!r} should be filtered"

    def test_brand_keywords_filtered(self, ocr_mod):
        assert ocr_mod.is_header_noise("GOURMET de GALLERIA")
        assert ocr_mod.is_header_noise("Weekly Menu")
        assert ocr_mod.is_header_noise("고메드갤러리아")
        assert ocr_mod.is_header_noise("정반식당")

    def test_logo_ocr_noise_filtered(self, ocr_mod):
        """브랜드 로고 오인식 노이즈가 필터돼야 합니다."""
        assert ocr_mod.is_header_noise("21 Y L")
        assert ocr_mod.is_header_noise("ABC")
        assert ocr_mod.is_header_noise("X1")

    def test_menu_text_not_filtered(self, ocr_mod):
        """실제 메뉴 텍스트는 노이즈로 분류되면 안 됩니다."""
        valid_menus = [
            "미트소스 스파게티",
            "버섯 곤드레모듬나물밥",
            "추가밥",
            "콩나물된장국",
            "쌀밥",
            "데리야끼 베이비크랩강정",
            "콩나물불고기",
            "솔방울 오징어초무침",
        ]
        for m in valid_menus:
            assert not ocr_mod.is_header_noise(m), f"{m!r} should NOT be filtered"


class TestExcludedRowKeywords:
    def test_take_out_excluded(self, ocr_mod):
        assert ocr_mod.is_excluded_row_start("TAKE OUT 프레쉬 BOX")
        assert ocr_mod.is_excluded_row_start("TAKE OUT HEATHY MEAL")
        assert ocr_mod.is_excluded_row_start("TAKE")

    def test_fresh_box_excluded(self, ocr_mod):
        assert ocr_mod.is_excluded_row_start("프레시 박스")
        assert ocr_mod.is_excluded_row_start("프레쉬박스")
        assert ocr_mod.is_excluded_row_start("헬시밀")

    def test_menu_items_not_excluded(self, ocr_mod):
        """일반 메뉴 아이템은 제외되면 안 됩니다."""
        valid = ["추가밥", "쌀밥", "미트소스 스파게티", "고추지무침"]
        for m in valid:
            assert not ocr_mod.is_excluded_row_start(m), f"{m!r} should NOT be excluded"


class TestFooterFilter:
    def test_footer_detected(self, ocr_mod):
        assert ocr_mod.is_footer("* 문의사항: 정다혜매니저")
        assert ocr_mod.is_footer("* 메뉴 판매는 식재")
        assert ocr_mod.is_footer("※ 알러지")

    def test_menu_not_footer(self, ocr_mod):
        assert not ocr_mod.is_footer("미트소스 스파게티")
        assert not ocr_mod.is_footer("추가밥")


class TestExcludedSectionKeywords:
    def test_take_out_in_section_keywords(self, ocr_mod):
        """TAKE OUT이 섹션 제외 키워드에 포함돼야 합니다."""
        assert "TAKE OUT" in ocr_mod.EXCLUDED_SECTION_KEYWORDS
        assert "TAKE" in ocr_mod.EXCLUDED_SECTION_KEYWORDS

    def test_heathy_in_section_keywords(self, ocr_mod):
        assert "헬시밀" in ocr_mod.EXCLUDED_SECTION_KEYWORDS


# ──────────────────────────────────────────────
# OCR 통합 테스트 (Surya 모델 필요)
# ──────────────────────────────────────────────

@pytest.mark.skipif(SKIP_OCR, reason="SKIP_OCR_MODEL=1 설정됨 (Surya 모델 불필요 모드)")
class TestOcrIntegration:
    @pytest.fixture(scope="class")
    def fixture_image_path(self):
        if not FIXTURE_IMAGE.exists():
            pytest.skip(f"fixture 이미지 없음: {FIXTURE_IMAGE}")
        return str(FIXTURE_IMAGE)

    def _run_ocr_script(self, image_path: str, weekday_idx: int, debug: bool = False) -> dict:
        """ocr-menu.py를 subprocess로 실행하고 JSON 결과를 반환합니다."""
        cmd = [sys.executable, str(REPO_ROOT / "scripts" / "ocr-menu.py"), image_path, str(weekday_idx)]
        if debug:
            cmd.append("--debug")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        # 마지막 JSON 라인 파싱
        lines = result.stdout.strip().split("\n")
        json_line = next((l for l in reversed(lines) if l.strip().startswith("{")), None)
        assert json_line is not None, (
            f"stdout에서 JSON을 찾을 수 없습니다.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        return json.loads(json_line)

    @pytest.mark.parametrize("weekday_idx,weekday_name", [
        (0, "월"), (1, "화"), (2, "수"), (3, "목"), (4, "금")
    ])
    def test_menu_extracted_for_each_day(self, fixture_image_path, weekday_idx, weekday_name):
        """월~금 각 요일 메뉴가 정상 추출되는지 검증합니다."""
        data = self._run_ocr_script(fixture_image_path, weekday_idx)

        assert data["success"] is True, f"OCR 실패: {data.get('error')}"
        assert data["weekday"] == weekday_name
        assert not data["is_holiday"], f"{weekday_name}요일이 공휴일로 잘못 감지됨"
        assert len(data["menu"]) >= 3, (
            f"{weekday_name}요일 메뉴 수가 너무 적음: {data['menu']}"
        )

    @pytest.mark.parametrize("weekday_idx", [0, 1, 2, 3, 4])
    def test_special_menu_included(self, fixture_image_path, weekday_idx):
        """특선 메뉴(핑크 배경 행)가 메뉴 목록에 포함되는지 검증합니다."""
        data = self._run_ocr_script(fixture_image_path, weekday_idx)

        assert data["success"] is True
        assert not data["is_holiday"]

        expected_special = EXPECTED_SPECIALS[weekday_idx]
        menu_joined = " ".join(data["menu"])
        # 특선 메뉴 텍스트가 완전 일치 또는 포함 여부 확인 (OCR 오차 허용)
        found = expected_special in data["menu"] or any(
            expected_special[:4] in item for item in data["menu"]
        )
        assert found, (
            f"[{WEEKDAY_NAMES[weekday_idx]}] 특선 메뉴 미포함.\n"
            f"기대: {expected_special!r}\n"
            f"추출된 메뉴: {data['menu']}"
        )

    @pytest.mark.parametrize("weekday_idx", [0, 1, 2, 3, 4])
    def test_representative_menu_item(self, fixture_image_path, weekday_idx):
        """각 요일의 대표 메뉴 아이템이 추출 결과에 포함되는지 검증합니다."""
        data = self._run_ocr_script(fixture_image_path, weekday_idx)

        assert data["success"] is True
        expected_item = EXPECTED_MENU_ITEMS[weekday_idx]
        assert expected_item in data["menu"], (
            f"[{WEEKDAY_NAMES[weekday_idx]}] {expected_item!r} 미포함.\n"
            f"추출된 메뉴: {data['menu']}"
        )

    def test_take_out_not_included(self, fixture_image_path):
        """TAKE OUT 섹션 메뉴가 결과에 포함되지 않아야 합니다."""
        for weekday_idx in range(5):
            data = self._run_ocr_script(fixture_image_path, weekday_idx)
            if not data["success"] or data["is_holiday"]:
                continue
            for item in data["menu"]:
                assert "TAKE" not in item.upper(), (
                    f"[{WEEKDAY_NAMES[weekday_idx]}] TAKE OUT 텍스트가 포함됨: {item!r}"
                )
                assert "프레쉬" not in item and "헬시밀" not in item, (
                    f"[{WEEKDAY_NAMES[weekday_idx]}] 제외 섹션 텍스트 포함: {item!r}"
                )


WEEKDAY_NAMES = ["월", "화", "수", "목", "금"]
