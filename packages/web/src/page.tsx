import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { BRAND } from "./site";

/** Whether the reader has moved to another page since the app loaded. */
export const NavigatedContext = createContext(false);

/** Name the tab after the page: "{page} · {archive}". */
export function useTitle(page: string): void {
  useEffect(() => {
    document.title = `${page} · ${BRAND.name}`;
  }, [page]);
}

/**
 * The page's h1. When it appears after the reader moved to another page, focus moves to it, so
 * the next Tab starts on the new page and a screen reader announces it.
 */
export function PageHeading({ children }: { children: ReactNode }) {
  const navigated = useContext(NavigatedContext);
  const [focusOnMount] = useState(navigated);
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focusOnMount) ref.current?.focus();
  }, [focusOnMount]);
  return (
    <h1 ref={ref} tabIndex={-1}>
      {children}
    </h1>
  );
}

/**
 * A modal dialog: it overlays the page, so opening it moves nothing. Escape or `onClose`
 * closes it, and focus goes back where it was.
 */
export function Modal({
  label,
  onClose,
  wide = false,
  children,
}: {
  label: string;
  onClose: () => void;
  wide?: boolean;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    const back = document.activeElement as HTMLElement | null;
    if (element && !element.open) element.showModal();
    return () => back?.focus();
  }, []);
  return (
    <dialog
      ref={dialog}
      className={wide ? "modal wide" : "modal"}
      aria-labelledby={label}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      {children}
    </dialog>
  );
}
