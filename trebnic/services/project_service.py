import uuid
from typing import Optional

from database import db
from models.entities import AppState, Project


class ProjectService:
    """Service for project operations.

    Handles project CRUD operations with database persistence.
    All data operations are async.
    """

    def __init__(self, state: AppState) -> None:
        self.state = state

    def validate_project_name(self, name: str, editing_id: Optional[str] = None) -> Optional[str]:
        """Validate a project name.

        Returns an error message if invalid, None if valid.
        """
        if not name:
            return "Name required"
        for p in self.state.projects:
            if p.name.lower() == name.lower() and p.id != editing_id:
                return "Project already exists"
        return None

    def generate_project_id(self, name: str) -> str:
        """Generate a unique project ID."""
        return str(uuid.uuid4())[:8]

    async def save_project(self, project: Project) -> None:
        """Save a project to the database."""
        await db.save_project(project.to_dict())

    async def delete_project(self, project_id: str) -> int:
        """Delete a project and all its tasks.

        Returns count of tasks deleted.
        """
        count = await db.delete_project(project_id)
        self.state.projects = [p for p in self.state.projects if p.id != project_id]
        return count
