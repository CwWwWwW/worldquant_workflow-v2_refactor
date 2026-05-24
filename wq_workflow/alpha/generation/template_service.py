from __future__ import annotations

class TemplateService:
    def split_and_store(self, *args, **kwargs):
        from wq_workflow.templates import split_and_store_templates

        return split_and_store_templates(*args, **kwargs)
