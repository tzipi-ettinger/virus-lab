// Text contrast where axe can't tell: text on a gradient, or in a box that has a
// decorative ::before/::after stripe. axe marks those "incomplete" and lets them
// pass. Here the text is hidden, the area it covers is photographed, and its color
// is measured against every pixel behind it: the worst pixel counts.
// Owner: shared

import type { Page } from "@playwright/test";

type Rgba = [number, number, number, number];

export interface Contrast {
  ratio: number;
  /** 4.5:1, or 3:1 for large text (WCAG 2.0, 1.4.3). */
  required: number;
}

/** The worst contrast of the element's own text, or null if it has no visible text. */
export async function measureContrast(page: Page, selector: string): Promise<Contrast | null> {
  const element = page.locator(selector).first();
  if (!(await element.isVisible())) return null;

  const measured = await element.evaluate((node: HTMLElement) => {
    // Colors as they rest, not partway through a transition.
    for (const animation of document.getAnimations()) if (animation instanceof CSSTransition) animation.finish();
    node.scrollIntoView({ block: "center", inline: "center" });
    const style = getComputedStyle(node);
    const rgba = (css: string): Rgba => {
      const [r, g, b, a = 1] = (css.match(/[\d.]+/g) ?? []).map(Number);
      return [r, g, b, a];
    };
    // Text painted with a gradient (background-clip: text, color: transparent) has
    // every stop as a color.
    const gradientText = rgba(style.color)[3] === 0 && style.backgroundImage.includes("gradient");
    const colors = gradientText
      ? (style.backgroundImage.match(/rgba?\([^)]+\)/g) ?? []).map(rgba)
      : [rgba(style.color)];

    // The box of the element's own text, not its padding or border.
    const range = document.createRange();
    const boxes: DOMRect[] = [];
    for (const child of node.childNodes) {
      if (child.nodeType !== Node.TEXT_NODE || !child.textContent?.trim()) continue;
      range.selectNodeContents(child);
      boxes.push(...range.getClientRects());
    }
    if (!boxes.length || !colors.length) return null;
    const left = Math.ceil(Math.max(0, Math.min(...boxes.map((b) => b.left))));
    const top = Math.ceil(Math.max(0, Math.min(...boxes.map((b) => b.top))));
    const right = Math.floor(Math.min(innerWidth, Math.max(...boxes.map((b) => b.right))));
    const bottom = Math.floor(Math.min(innerHeight, Math.max(...boxes.map((b) => b.bottom))));
    if (right - left < 1 || bottom - top < 1) return null;

    // Hide all the text on the page, not only this element's: a line box can reach
    // into the line above, and the edges of its letters would count as background.
    // Icons inside the element go too. Through the CSSOM, which the page's
    // Content-Security-Policy allows (a <style> tag it would block).
    const all = [...document.querySelectorAll<HTMLElement | SVGElement>("body, body *")];
    // Gradient text is found before anything changes: once a parent's color is
    // transparent, a child that inherits it would look like gradient text too.
    const gradientTexts = new Set(
      all.filter((el) => {
        const own = getComputedStyle(el);
        return rgba(own.color)[3] === 0 && own.backgroundImage.includes("gradient");
      }),
    );
    const saved = new Map<HTMLElement | SVGElement, string>();
    (window as unknown as { contrastSaved: typeof saved }).contrastSaved = saved;
    for (const el of all) {
      saved.set(el, el.style.cssText);
      if (gradientTexts.has(el)) el.style.setProperty("background-image", "none", "important");
      el.style.setProperty("color", "transparent", "important");
      el.style.setProperty("-webkit-text-fill-color", "transparent", "important");
      el.style.setProperty("text-shadow", "none", "important");
      el.style.setProperty("caret-color", "transparent", "important");
      if (node.contains(el) && (el instanceof SVGElement || el instanceof HTMLImageElement)) {
        el.style.setProperty("visibility", "hidden", "important");
      }
    }

    const size = parseFloat(style.fontSize);
    const large = size >= 24 || (Number(style.fontWeight) >= 700 && size >= 18.66);
    return { colors, required: large ? 3 : 4.5, clip: { x: left, y: top, width: right - left, height: bottom - top } };
  });
  if (!measured) return null;

  let png: Buffer;
  try {
    png = await page.screenshot({ clip: measured.clip, scale: "css", animations: "disabled", caret: "hide" });
  } finally {
    await page.evaluate(() => {
      const holder = window as unknown as { contrastSaved?: Map<HTMLElement | SVGElement, string> };
      for (const [el, cssText] of holder.contrastSaved ?? []) el.style.cssText = cssText;
      delete holder.contrastSaved;
      // A "transition: color" would fade the text back in from transparent, and the
      // next element (or axe, on the next screen) would read it half faded.
      for (const animation of document.getAnimations()) if (animation instanceof CSSTransition) animation.finish();
    });
  }

  // Decoded by the browser, through an <img>: the page's CSP allows data: images
  // (img-src), not fetch() of them (connect-src).
  const ratio = await page.evaluate(
    async ({ base64, colors }) => {
      const image = new Image();
      image.src = `data:image/png;base64,${base64}`;
      await image.decode();
      const canvas = new OffscreenCanvas(image.naturalWidth, image.naturalHeight);
      const context = canvas.getContext("2d")!;
      context.drawImage(image, 0, 0);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;

      const channel = (c: number) => {
        const s = c / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      };
      const luminance = (r: number, g: number, b: number) =>
        0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);

      let worst = 21;
      for (let i = 0; i < pixels.length; i += 4) {
        const [br, bg, bb] = [pixels[i], pixels[i + 1], pixels[i + 2]];
        const back = luminance(br, bg, bb);
        for (const [r, g, b, a] of colors) {
          // A see-through text color is what it looks like on this pixel.
          const front = luminance(r * a + br * (1 - a), g * a + bg * (1 - a), b * a + bb * (1 - a));
          const ratio = (Math.max(front, back) + 0.05) / (Math.min(front, back) + 0.05);
          if (ratio < worst) worst = ratio;
        }
      }
      return worst;
    },
    { base64: png.toString("base64"), colors: measured.colors },
  );
  return { ratio, required: measured.required };
}
