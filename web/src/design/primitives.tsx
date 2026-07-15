import {
  forwardRef,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";

export const VisuallyHidden = ({ children, ...props }: HTMLAttributes<HTMLSpanElement>): ReactNode => (
  <span className="visually-hidden" {...props}>{children}</span>
);

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, children, className = "", type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={`icon-button focus-ring ${className}`.trim()}
      aria-label={label}
      {...props}
    >
      {children}
    </button>
  );
});

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  description?: string;
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, description, id, className = "", ...props },
  ref,
) {
  const fieldId = id ?? `field-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  const descriptionId = description ? `${fieldId}-description` : undefined;
  return (
    <div className="field">
      <label htmlFor={fieldId} className="field__label">{label}</label>
      <input
        ref={ref}
        id={fieldId}
        className={`field__control focus-ring ${className}`.trim()}
        aria-describedby={descriptionId}
        {...props}
      />
      {description ? <p id={descriptionId} className="field__description">{description}</p> : null}
    </div>
  );
});

export const ModalPortalHost = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(function ModalPortalHost(props, ref) {
  return <div ref={ref} id="dropfinder-overlay-host" data-overlay-host {...props} />;
});
