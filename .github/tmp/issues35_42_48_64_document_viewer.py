from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


capability = "web/src/platform/documents/document-viewer-capability.js"
replace_once(
    capability,
    """    this.setState({
      status: 'loading', type, documentRef, context, page: 1, pages: null,
      scale: this.options.initialScale, fitWidth: true, displayUrl: null, error: null, sessionId,
    });
""",
    """    this.setState({
      status: 'loading', type, documentRef, context, page: 1, pages: null,
      scale: this.options.initialScale, renderedScale: this.options.initialScale,
      fitWidth: true, displayUrl: null, error: null, sessionId,
    });
""",
)
replace_once(
    capability,
    """      await renderTask.promise;
      assertCurrentRender(this, session, request.revision);
      return { page: request.page, scale: effectiveScale, width: viewport.width, height: viewport.height };
""",
    """      await renderTask.promise;
      assertCurrentRender(this, session, request.revision);
      if (this.state.sessionId === session.id && this.state.renderedScale !== effectiveScale) {
        this.setState({ ...this.state, renderedScale: effectiveScale });
      }
      return { page: request.page, scale: effectiveScale, width: viewport.width, height: viewport.height };
""",
)
replace_once(
    capability,
    """  zoomIn() { this.setZoom(this.state.scale + 0.25); }
  zoomOut() { this.setZoom(this.state.scale - 0.25); }
  resetZoom() { this.setState({ ...this.state, scale: this.options.initialScale, fitWidth: false }); }
  setFitWidth(enabled = true) { this.setState({ ...this.state, fitWidth: Boolean(enabled) }); }
  setZoom(scale) { this.setState({ ...this.state, scale: clamp(scale, this.options.minScale, this.options.maxScale), fitWidth: false }); }
""",
    """  zoomIn() { this.setZoom((this.state.renderedScale ?? this.state.scale) + 0.25); }
  zoomOut() { this.setZoom((this.state.renderedScale ?? this.state.scale) - 0.25); }
  resetZoom() {
    this.setState({
      ...this.state,
      scale: this.options.initialScale,
      renderedScale: this.options.initialScale,
      fitWidth: false,
    });
  }
  setFitWidth(enabled = true) { this.setState({ ...this.state, fitWidth: Boolean(enabled) }); }
  setZoom(scale) {
    const nextScale = clamp(scale, this.options.minScale, this.options.maxScale);
    this.setState({ ...this.state, scale: nextScale, renderedScale: nextScale, fitWidth: false });
  }
""",
)
replace_once(
    capability,
    """function closedState() { return Object.freeze({ status: 'closed', type: null, documentRef: null, context: null, page: 1, pages: null, scale: 1, fitWidth: true, displayUrl: null, error: null, sessionId: null }); }
""",
    """function closedState() { return Object.freeze({ status: 'closed', type: null, documentRef: null, context: null, page: 1, pages: null, scale: 1, renderedScale: 1, fitWidth: true, displayUrl: null, error: null, sessionId: null }); }
""",
)

integration = "web/src/features/integration/register-marketplace-props.tsx"
replace_once(
    integration,
    """  scale: number;
  fitWidth: boolean;
""",
    """  scale: number;
  renderedScale: number;
  fitWidth: boolean;
""",
)
replace_once(
    integration,
    """  zoomIn(): void;
  zoomOut(): void;
  setFitWidth(enabled?: boolean): void;
""",
    """  zoomIn(): void;
  zoomOut(): void;
  resetZoom(): void;
  setFitWidth(enabled?: boolean): void;
""",
)
replace_once(integration, "function DocumentOverlay({\n", "export function DocumentOverlay({\n")
replace_once(
    integration,
    """  const dialogRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
""",
    """  const dialogRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const closingRef = useRef(false);
  const lastStageWidthRef = useRef(0);
  const [resizeRevision, setResizeRevision] = useState(0);
  const [renderError, setRenderError] = useState<string | null>(null);
""",
)
replace_once(
    integration,
    """  useEffect(() => {
    if (state.status !== "ready" || state.type !== "pdf" || !canvasRef.current) return;
    let current = true;
    setRenderError(null);
    void viewer.renderPage(canvasRef.current, {
      page: state.page,
      scale: state.scale,
      fitWidth: state.fitWidth,
    }).catch((error: unknown) => {
      if (current && stringValue(objectValue(error)?.name) !== "AbortError") {
        setRenderError("This document could not be rendered. Open the original document.");
      }
    });
    return () => {
      current = false;
    };
  }, [state.fitWidth, state.page, state.scale, state.sessionId, state.status, state.type, viewer]);

  const close = async () => {
    await viewer.close();
    onClosed();
  };
""",
    """  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || state.status !== "ready" || state.type !== "pdf" || !state.fitWidth || typeof ResizeObserver === "undefined") return;
    lastStageWidthRef.current = Math.round(stage.getBoundingClientRect().width);
    let scheduled = false;
    const observer = new ResizeObserver((entries) => {
      const width = Math.round(entries[0]?.contentRect.width ?? stage.getBoundingClientRect().width);
      if (!width || Math.abs(width - lastStageWidthRef.current) < 2 || scheduled) return;
      lastStageWidthRef.current = width;
      scheduled = true;
      queueMicrotask(() => {
        scheduled = false;
        setResizeRevision((value) => value + 1);
      });
    });
    observer.observe(stage);
    return () => observer.disconnect();
  }, [state.fitWidth, state.sessionId, state.status, state.type]);

  useEffect(() => {
    if (state.status !== "ready" || state.type !== "pdf" || !canvasRef.current) return;
    let current = true;
    setRenderError(null);
    void viewer.renderPage(canvasRef.current, {
      page: state.page,
      scale: state.scale,
      fitWidth: state.fitWidth,
    }).catch((error: unknown) => {
      if (current && stringValue(objectValue(error)?.name) !== "AbortError") {
        setRenderError("This document could not be rendered. Open the original document.");
      }
    });
    return () => {
      current = false;
    };
  }, [resizeRevision, state.fitWidth, state.page, state.scale, state.sessionId, state.status, state.type, viewer]);

  const close = async () => {
    if (closingRef.current) return;
    closingRef.current = true;
    const invoker = request.invokingElement;
    await viewer.close({ restoreFocus: false });
    onClosed();
    await Promise.resolve();
    if (invoker?.isConnected) invoker.focus({ preventScroll: true });
  };
""",
)
replace_once(
    integration,
    """        onKeyDown={(event) => viewer.handleKeyDown(event.nativeEvent, dialogRef.current)}
""",
    """        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            void close();
            return;
          }
          viewer.handleKeyDown(event.nativeEvent, dialogRef.current);
        }}
""",
)
replace_once(
    integration,
    """        <div className="df-platform-document-stage">
""",
    """        <div ref={stageRef} className="df-platform-document-stage">
""",
)
replace_once(
    integration,
    """            <button type="button" onClick={() => viewer.zoomOut()}>Zoom out</button>
            <button type="button" onClick={() => viewer.zoomIn()}>Zoom in</button>
            <button type="button" onClick={() => viewer.setFitWidth(true)}>Fit width</button>
""",
    """            <button type="button" onClick={() => viewer.zoomOut()}>Zoom out</button>
            <button type="button" onClick={() => viewer.zoomIn()}>Zoom in</button>
            <button type="button" onClick={() => viewer.resetZoom()}>Reset zoom</button>
            <button type="button" onClick={() => viewer.setFitWidth(true)}>Fit width</button>
""",
)
