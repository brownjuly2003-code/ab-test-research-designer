import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";

(
  globalThis as typeof globalThis & {
    IS_REACT_ACT_ENVIRONMENT?: boolean;
  }
).IS_REACT_ACT_ENVIRONMENT = true;

type RenderResult = {
  container: HTMLDivElement;
  rerender: (ui: ReactElement) => Promise<void>;
  unmount: () => Promise<void>;
};

export async function renderIntoDocument(ui: ReactElement): Promise<RenderResult> {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  async function render(uiToRender: ReactElement) {
    await act(async () => {
      root.render(uiToRender);
    });
  }

  await render(ui);

  return {
    container,
    rerender: render,
    async unmount() {
      await act(async () => {
        root.unmount();
      });
      container.remove();
    }
  };
}

export async function flushEffects(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
  });
}

export function findButton(container: HTMLElement, label: string): HTMLButtonElement {
  const button = Array.from(container.querySelectorAll("button")).find(
    (candidate) => candidate.textContent?.trim() === label
  );

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Button not found: ${label}`);
  }

  return button;
}

export function findButtonByAriaLabel(container: HTMLElement, label: string): HTMLButtonElement {
  const button = container.querySelector(`button[aria-label="${label}"]`);

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Button with aria-label not found: ${label}`);
  }

  return button;
}

export async function click(element: HTMLElement): Promise<void> {
  await act(async () => {
    element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

export async function changeValue(element: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, value: string): Promise<void> {
  const prototype =
    element instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : element instanceof HTMLSelectElement
        ? HTMLSelectElement.prototype
        : HTMLInputElement.prototype;
  const valueSetter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;

  await act(async () => {
    valueSetter?.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
