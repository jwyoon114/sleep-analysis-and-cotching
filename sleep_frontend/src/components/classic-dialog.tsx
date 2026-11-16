"use client";

import {useId, useLayoutEffect, useRef, type ReactNode} from "react";
import {X} from "lucide-react";

type Props = {
  title: string;
  description?: string;
  children: ReactNode;
  onDismiss: () => void;
  open?: boolean;
  busy?: boolean;
  wide?: boolean;
  alert?: boolean;
  className?: string;
  closeLabel?: string;
};

export default function ClassicDialog({title,description,children,onDismiss,open=true,busy=false,wide=false,alert=false,className="",closeLabel="닫기"}:Props) {
  const id=useId();
  const dialog=useRef<HTMLDialogElement>(null);
  const heading=useRef<HTMLHeadingElement>(null);

  useLayoutEffect(()=>{
    const node=dialog.current;
    if(!open||!node)return;
    const opener=document.activeElement;
    node.showModal();
    heading.current?.focus({preventScroll:true});
    return ()=>{
      node.close();
      if(opener instanceof HTMLElement&&opener.isConnected)opener.focus({preventScroll:true});
    };
  },[open]);

  return <dialog ref={dialog} className={`classic-dialog ${wide?"classic-dialog-wide":""} ${className}`}
    aria-labelledby={id} aria-describedby={description?id+"-description":undefined} role={alert?"alertdialog":undefined}
    onCancel={event=>{event.preventDefault();if(!busy)onDismiss();}}>
    <div className="classic-dialog-header">
      <div><h2 id={id} ref={heading} tabIndex={-1}>{title}</h2>
        {description&&<p id={id+"-description"}>{description}</p>}</div>
      <button type="button" className="icon-button" aria-label={closeLabel} disabled={busy} onClick={onDismiss}><X size={20} aria-hidden="true"/></button>
    </div>
    <div className="classic-dialog-content">{children}</div>
  </dialog>;
}
