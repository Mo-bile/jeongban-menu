/**
 * 네이버 지도 place 피드에서 첫 번째(최신) 피드 항목을 Playwright로 파싱합니다.
 * SPA이므로 headless 브라우저로 렌더링 후 DOM에서 추출합니다.
 */

const DEFAULT_PLACE_URL =
  "https://map.naver.com/p/entry/place/1671594903?placePath=%2Ffeed";

const FEED_ITEM_SELECTOR = ".place_section_content ul li.place_apply_pui";
const TITLE_SELECTOR = ".pui__dGLDWy";
const IMAGE_SELECTOR = ".place_thumb img";
const BODY_SELECTOR = '.pui__vn15t2 a[data-pui-click-code="text"]';
const TIME_SELECTOR = "time";

/**
 * 첫 번째 피드 li 요소에서 제목, 이미지, 본문, 시간을 추출합니다.
 * @param {import('playwright').Page} page
 * @returns {Promise<{ title: string; imageUrl: string; body: string; time: string } | null>}
 */
async function extractFirstFeedItem(page) {
  return page.evaluate(
    ({ feedSelector, titleSel, imageSel, bodySel, timeSel }) => {
      const li = document.querySelector(feedSelector);
      if (!li) return null;

      const titleEl = li.querySelector(titleSel);
      let title = titleEl ? titleEl.textContent.trim() : "";
      if (title.startsWith("알림")) title = title.slice(2).trim();

      const imgEl = li.querySelector(imageSel);
      const imageUrl = imgEl ? imgEl.getAttribute("src") || "" : "";

      const bodyEl = li.querySelector(bodySel);
      const body = bodyEl ? bodyEl.textContent.trim() : "";

      const timeEl = li.querySelector(timeSel);
      const time = timeEl ? timeEl.textContent.trim() : "";

      return { title, imageUrl, body, time };
    },
    {
      feedSelector: FEED_ITEM_SELECTOR,
      titleSel: TITLE_SELECTOR,
      imageSel: IMAGE_SELECTOR,
      bodySel: BODY_SELECTOR,
      timeSel: TIME_SELECTOR,
    }
  );
}

/**
 * 네이버 지도 place 피드 URL에 접속해 최신(첫 번째) 피드 항목을 수집합니다.
 * @param {Object} options
 * @param {string} [options.placeUrl] - place 피드 URL (기본값: 정반식당 피드)
 * @param {number} [options.timeout] - 피드 로딩 대기 타임아웃(ms)
 * @param {boolean} [options.headless] - headless 여부
 * @returns {Promise<{ title: string; imageUrl: string; body: string; time: string } | null>}
 */
export async function fetchLatestFeedItem(options = {}) {
  const {
    placeUrl = process.env.PLACE_URL || DEFAULT_PLACE_URL,
    timeout = 15000,
    headless = true,
  } = options;

  const { chromium } = await import("playwright");
  const browser = await chromium.launch({ headless });

  try {
    const context = await browser.newContext({
      userAgent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      viewport: { width: 1280, height: 800 },
    });
    const page = await context.newPage();

    await page.goto(placeUrl, { waitUntil: "load", timeout: 25000 });
    await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});

    let targetPage = page;
    const frames = page.frames();
    for (const frame of frames) {
      try {
        const loc = frame.locator(FEED_ITEM_SELECTOR).first();
        await loc.waitFor({ state: "visible", timeout: 3000 });
        targetPage = frame;
        break;
      } catch {
        continue;
      }
    }

    await targetPage.waitForSelector(FEED_ITEM_SELECTOR, { timeout });
    const item = await extractFirstFeedItem(targetPage);
    return item;
  } finally {
    await browser.close();
  }
}
