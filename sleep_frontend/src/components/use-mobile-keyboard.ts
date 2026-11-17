"use client";

import {useEffect, useState} from "react";

const keyboardInputs = ':is(.mobile-app,.classic-dialog) :is(textarea,input:not([type]),input:is([type="text"],[type="search"],[type="email"],[type="password"],[type="number"],[type="tel"],[type="url"]))';

export function useMobileKeyboard() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const mobile = window.matchMedia("(max-width: 760px) and (pointer: coarse)");
    let layoutWidth = window.innerWidth;
    let fullHeight = viewport.height;
    let reveal = 0;
    const root = document.documentElement;

    function update() {
      if (!viewport) return;
      if (window.innerWidth !== layoutWidth) {
        layoutWidth = window.innerWidth;
        fullHeight = viewport.height;
      }
      const unzoomed = Math.abs(1 - viewport.scale) < .02;
      if (unzoomed) fullHeight = Math.max(fullHeight, viewport.height);
      const field = document.activeElement;
      const typing = field instanceof HTMLElement && field.matches(keyboardInputs);
      const keyboard = mobile.matches && typing && unzoomed && fullHeight - viewport.height >= 150;
      cancelAnimationFrame(reveal);
      if (keyboard) {
        root.style.setProperty("--keyboard-inset", Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop) + "px");
        reveal = requestAnimationFrame(() => {
          const rect = field.getBoundingClientRect();
          if (rect.bottom > viewport.offsetTop + viewport.height - 12 || rect.top < viewport.offsetTop) {
            field.scrollIntoView({block:"nearest",inline:"nearest"});
          }
        });
      } else root.style.removeProperty("--keyboard-inset");
      setOpen(keyboard);
    }

    viewport.addEventListener("resize", update);
    window.addEventListener("resize", update);
    mobile.addEventListener("change", update);
    document.addEventListener("focusin", update);
    document.addEventListener("focusout", update);
    return () => {
      cancelAnimationFrame(reveal);
      root.style.removeProperty("--keyboard-inset");
      viewport.removeEventListener("resize", update);
      window.removeEventListener("resize", update);
      mobile.removeEventListener("change", update);
      document.removeEventListener("focusin", update);
      document.removeEventListener("focusout", update);
    };
  }, []);

  return open;
}
