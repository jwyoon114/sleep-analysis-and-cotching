"use client";

import {useEffect, useState} from "react";

const keyboardInputs = '.mobile-app :is(textarea, input:not([type]), input:is([type="text"],[type="search"],[type="email"],[type="password"],[type="number"],[type="tel"],[type="url"]))';

export function useMobileKeyboard() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const mobile = window.matchMedia("(max-width: 760px) and (pointer: coarse)");
    let layoutWidth = window.innerWidth;
    let fullHeight = viewport.height;
    let previouslyOpen = false;

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
      if (keyboard && !previouslyOpen && field.getBoundingClientRect().bottom > viewport.offsetTop + viewport.height - 12) {
        field.scrollIntoView({block:"center", inline:"nearest"});
      }
      previouslyOpen = keyboard;
      setOpen(keyboard);
    }

    viewport.addEventListener("resize", update);
    window.addEventListener("resize", update);
    mobile.addEventListener("change", update);
    document.addEventListener("focusin", update);
    document.addEventListener("focusout", update);
    return () => {
      viewport.removeEventListener("resize", update);
      window.removeEventListener("resize", update);
      mobile.removeEventListener("change", update);
      document.removeEventListener("focusin", update);
      document.removeEventListener("focusout", update);
    };
  }, []);

  return open;
}
