declare module "react" {
  export type Dispatch<T> = (value: T | ((current: T) => T)) => void;
  export function useEffect(effect: () => void | (() => void), dependencies?: readonly unknown[]): void;
  export function useId(): string;
  export function useMemo<T>(factory: () => T, dependencies: readonly unknown[]): T;
  export function useRef<T>(value: T): { current: T };
  export function useState<T>(value: T | (() => T)): [T, Dispatch<T>];
}

declare module "*.css";

declare namespace JSX {
  interface Element {}
  interface IntrinsicAttributes { key?: string | number; }
  interface IntrinsicElements {
    [elementName: string]: any;
  }
}
