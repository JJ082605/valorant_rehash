"""CustomTkinter window. Presentation only — all logic lives in applier.py."""

from __future__ import annotations

import logging
import queue
import threading
from tkinter import messagebox

import customtkinter as ctk

from .applier import Applier
from .errors import ValoError
from .riot_client import Session

log = logging.getLogger(__name__)


class App(ctk.CTk):
    def __init__(self, applier: Applier):
        super().__init__()
        self.applier = applier
        self.session: Session | None = None
        self.selected: str | None = None
        self.busy = False

        self.title("VALORANT Settings Applier")
        self.geometry("520x480")
        self.minsize(420, 380)

        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=12, pady=(12, 6))
        self.status = ctk.CTkLabel(top, text="Checking Riot Client…", anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=8, pady=8)
        self.refresh_btn = ctk.CTkButton(top, text="Refresh", width=80, command=self.refresh)
        self.refresh_btn.pack(side="right", padx=8)

        self.list_frame = ctk.CTkScrollableFrame(self, label_text="Profiles")
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=6)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=6)
        self.capture_btn = ctk.CTkButton(buttons, text="Capture", command=self.on_capture)
        self.apply_btn = ctk.CTkButton(buttons, text="Apply", command=self.on_apply)
        self.restore_btn = ctk.CTkButton(buttons, text="Restore last backup", command=self.on_restore)
        self.delete_btn = ctk.CTkButton(
            buttons, text="Delete profile", fg_color="gray30", command=self.on_delete
        )
        for i, b in enumerate((self.capture_btn, self.apply_btn, self.restore_btn, self.delete_btn)):
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=4, pady=4)
        buttons.grid_columnconfigure((0, 1), weight=1)

        self.result = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=480)
        self.result.pack(fill="x", padx=16, pady=(4, 12))

        # Workers never touch Tk; they post results here and the UI thread polls.
        self._results: queue.Queue = queue.Queue()
        self.after(50, self._poll)
        self.after(0, self.refresh)

    # --- helpers ---------------------------------------------------------------

    def _run(self, work, on_done) -> None:
        """Run `work` on a worker thread; deliver (result, error) to `on_done` on the UI thread."""
        if self.busy:
            return
        self.busy = True
        self._update_buttons()

        def target():
            try:
                res, err = work(), None
            except ValoError as e:
                log.info("%s: %s", type(e).__name__, e.user_message)
                res, err = None, e.user_message
            except Exception:
                log.exception("Unexpected error")
                res, err = None, "Something went wrong — see log.txt."
            self._results.put((on_done, res, err))

        threading.Thread(target=target, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                on_done, res, err = self._results.get_nowait()
                try:
                    self._finish(on_done, res, err)
                except Exception:
                    self.busy = False
                    log.exception("UI update failed")
        except queue.Empty:
            pass
        self.after(50, self._poll)

    def _finish(self, on_done, res, err) -> None:
        self.busy = False
        on_done(res, err)
        self._update_buttons()

    def _show(self, ok: bool, text: str) -> None:
        self.result.configure(text=("✅ " if ok else "❌ ") + text)

    def _update_buttons(self) -> None:
        signed_in = self.session is not None and not self.busy
        has_sel = self.selected is not None and not self.busy
        self.capture_btn.configure(state="normal" if signed_in else "disabled")
        self.apply_btn.configure(state="normal" if signed_in and has_sel else "disabled")
        self.restore_btn.configure(state="normal" if signed_in else "disabled")
        self.delete_btn.configure(state="normal" if has_sel else "disabled")
        self.refresh_btn.configure(state="disabled" if self.busy else "normal")

    def _reload_profiles(self) -> None:
        for w in self.list_frame.winfo_children():
            w.destroy()
        profiles, corrupt = self.applier.store.list()
        names = {p.name for p in profiles}
        if self.selected not in names:
            self.selected = None
        for p in profiles:
            text = f"{p.name}   —   from {p.source_riot_id}"
            btn = ctk.CTkButton(
                self.list_frame,
                text=text,
                anchor="w",
                fg_color=("gray75", "gray25") if p.name == self.selected else "transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"),
                command=lambda n=p.name: self._select(n),
            )
            btn.pack(fill="x", pady=1)
        if not profiles:
            ctk.CTkLabel(self.list_frame, text="No profiles yet — sign in and click Capture.").pack(pady=8)
        if corrupt:
            ctk.CTkLabel(
                self.list_frame,
                text="⚠ Skipped unreadable profile(s): " + ", ".join(corrupt),
                text_color="orange",
            ).pack(pady=4)
        self._update_buttons()

    def _select(self, name: str) -> None:
        self.selected = name
        self._reload_profiles()

    def _confirm_valorant_closed(self) -> bool:
        if not self.applier.valorant_running():
            return True
        return messagebox.askyesno(
            "VALORANT is running",
            "Close Valorant first or it may overwrite these settings.\n\nContinue anyway?",
        )

    # --- actions ---------------------------------------------------------------

    def refresh(self) -> None:
        def done(session, err):
            self.session = session
            if session:
                self.status.configure(text=f"Signed in as {session.riot_id}")
            else:
                self.status.configure(text=err or "Riot Client not running")
            self._reload_profiles()

        self._run(self.applier.current_session, done)

    def on_capture(self) -> None:
        if not self.session:
            return
        dialog = ctk.CTkInputDialog(text="Profile name:", title="Capture settings")
        name = dialog.get_input()
        if name is None:
            return
        name = name.strip() or self.session.riot_id
        overwrite = False
        try:
            if self.applier.store.exists(name):
                if not messagebox.askyesno("Overwrite?", f"Replace the existing profile '{name}'?"):
                    return
                overwrite = True
        except ValoError as e:
            self._show(False, e.user_message)
            return

        def done(profile, err):
            if err:
                self._show(False, err)
            else:
                self.selected = profile.name
                self._show(True, f"Captured '{profile.name}' from {profile.source_riot_id}.")
            self._reload_profiles()

        self._run(lambda: self.applier.capture(name, overwrite=overwrite), done)

    def on_apply(self) -> None:
        if not (self.session and self.selected):
            return
        profile, target = self.selected, self.session
        if not self._confirm_valorant_closed():
            return
        if not messagebox.askyesno(
            "Apply settings",
            f"Apply '{profile}' to {target.riot_id}? Current settings will be backed up.",
        ):
            return

        def done(res, err):
            if err:
                self._show(False, err)
            elif res.verified:
                self._show(True, f"Applied '{profile}' to {res.target_riot_id}. Backup saved.")
            else:
                self._show(False, f"Sent '{profile}' to {res.target_riot_id}, but the check afterwards didn't match. Backup saved.")

        self._run(lambda: self.applier.apply(profile, expected_puuid=target.puuid), done)

    def on_restore(self) -> None:
        if not self.session:
            return
        target = self.session
        if not self._confirm_valorant_closed():
            return
        if not messagebox.askyesno(
            "Restore backup",
            f"Restore the last backup for {target.riot_id}? Current settings will be backed up first.",
        ):
            return

        def done(res, err):
            if err:
                self._show(False, err)
            else:
                self._show(res.verified, f"Restored last backup for {res.target_riot_id}.")

        self._run(lambda: self.applier.restore_latest(expected_puuid=target.puuid), done)

    def on_delete(self) -> None:
        if not self.selected:
            return
        name = self.selected
        if not messagebox.askyesno("Delete profile", f"Delete profile '{name}'?"):
            return
        try:
            self.applier.store.delete(name)
        except ValoError as e:
            self._show(False, e.user_message)
            return
        self.selected = None
        self._show(True, f"Deleted '{name}'.")
        self._reload_profiles()
