"""Batched Tk projection. This module never owns capture selection."""
from collections import deque


class TreeProjection:
    BATCH_SIZE = 100
    PLACEHOLDER = "__lazy__:"

    def __init__(self, tree, insert_row):
        self.tree = tree
        self.insert_row = insert_row
        self.children = {}
        self.loaded = set()
        self.jobs = deque()
        self.timer = None
        self.epoch = 0
        self.restore = None
        tree.bind("<Destroy>", self._destroy, add=True)
        tree.bind("<ButtonPress-1>", self._user_navigation, add=True)
        tree.bind("<KeyPress>", self._user_navigation, add=True)
        tree.bind("<MouseWheel>", self._user_navigation, add=True)

    def _user_navigation(self, _event):
        self.restore = None

    def _destroy(self, event):
        if event.widget is self.tree and self.timer is not None:
            self.tree.after_cancel(self.timer)
            self.timer = None

    def rendered(self):
        pending = list(self.tree.get_children())
        while pending:
            iid = pending.pop()
            if not iid.startswith(self.PLACEHOLDER):
                yield iid
                pending.extend(self.tree.get_children(iid))

    def replace(self, rows):
        tree = self.tree
        opened = {iid for iid in self.rendered() if tree.item(iid, "open")}
        old_roots = set(tree.get_children())
        anchor = ("", 0)
        for y in range(tree.winfo_height()):
            iid = tree.identify_row(y)
            box = tree.bbox(iid) if iid else ()
            if box:
                anchor = (iid, box[1])
                break
        self.restore = (tree.focus(), tree.selection(), tree.yview()[0], anchor)
        self.epoch += 1
        if self.timer is not None:
            tree.after_cancel(self.timer)
            self.timer = None
        self.jobs.clear()
        self.loaded.clear()
        tree.delete(*tree.get_children())
        self.children = {}
        for row in rows:
            parent = str(row["parent"]) if row["parent"] is not None else ""
            self.children.setdefault(parent, []).append(row)
        roots = self.children.get("", ())
        self.opened = opened
        if not old_roots.intersection(str(row["path"]) for row in roots):
            self.opened = {str(row["path"]) for row in roots}
            self.restore = None
        self.jobs.append(("", iter(roots)))
        self._batch(self.epoch)

    def expand(self, iid):
        if iid in self.loaded or iid not in self.children:
            return
        self.loaded.add(iid)
        placeholder = self.PLACEHOLDER + iid
        if self.tree.exists(placeholder):
            self.tree.delete(placeholder)
        self.jobs.append((iid, iter(self.children[iid])))
        if self.timer is None:
            epoch = self.epoch
            self.timer = self.tree.after(1, lambda: self._batch(epoch))

    def _batch(self, epoch):
        if epoch != self.epoch:
            return
        self.timer = None
        count = 0
        while self.jobs and count < self.BATCH_SIZE:
            parent, iterator = self.jobs[0]
            if parent and not self.tree.item(parent, "open"):
                self.jobs.popleft()
                self.loaded.discard(parent)
                if not self.tree.get_children(parent):
                    self.tree.insert(parent, "end", iid=self.PLACEHOLDER + parent, text="Loading…")
                continue
            try:
                row = next(iterator)
            except StopIteration:
                self.jobs.popleft()
                continue
            iid = str(row["path"])
            count += 1
            if self.tree.exists(iid):
                continue
            self.insert_row(row)
            if iid in self.children:
                self.tree.insert(iid, "end", iid=self.PLACEHOLDER + iid, text="Loading…")
                if iid in self.opened:
                    self.tree.item(iid, open=True)
                    # Queue children without starting a second timer during this batch.
                    self.loaded.add(iid)
                    self.tree.delete(self.PLACEHOLDER + iid)
                    self.jobs.append((iid, iter(self.children[iid])))
        if self.jobs:
            self.timer = self.tree.after(1, lambda: self._batch(epoch))
        elif self.restore is not None:
            focus, selected, scroll, (anchor, anchor_y) = self.restore
            if self.tree.exists(focus):
                self.tree.focus(focus)
            self.tree.selection_set([iid for iid in selected if self.tree.exists(iid)])
            self.tree.yview_moveto(scroll)
            self.tree.update_idletasks()
            if anchor and self.tree.exists(anchor):
                box = self.tree.bbox(anchor)
                if not box:
                    self.tree.see(anchor)
                    self.tree.update_idletasks()
                    box = self.tree.bbox(anchor)
                if box:
                    self.tree.yview_scroll(round((box[1] - anchor_y) / box[3]), "units")
                    self.tree.update_idletasks()
            self.restore = None
