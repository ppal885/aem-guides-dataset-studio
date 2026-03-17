"""
Workflow data generation for AEM Guides datasets.

This module generates review workflow, translation workflow, and approval data.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json
from app.generator.generate import safe_join


class WorkflowDataGenerator:
    """Generate workflow metadata and data."""
    
    def __init__(self, config, rand):
        self.config = config
        self.rand = rand
    
    def generate_review_workflow_data(
        self,
        content_paths: List[str],
        reviewers: List[str] = None,
        workflow_status: str = "pending",
    ) -> Dict:
        """Generate review workflow data."""
        if reviewers is None:
            reviewers = ["reviewer1", "reviewer2", "reviewer3"]
        
        workflows = []
        
        for path in content_paths:
            workflow = {
                "contentPath": path,
                "workflowType": "review",
                "status": workflow_status,
                "created": self._iso_timestamp(),
                "createdBy": "admin",
                "reviewers": self.rand.sample(reviewers, min(len(reviewers), self.rand.randint(1, 3))),
                "assignee": self.rand.choice(reviewers) if reviewers else None,
                "dueDate": self._future_timestamp(days=7).isoformat(),
                "comments": [],
                "approvals": {},
            }
            
            # Add comments if workflow is in progress
            if workflow_status in ["in_progress", "reviewed"]:
                num_comments = self.rand.randint(1, 5)
                for i in range(num_comments):
                    comment = {
                        "id": f"comment_{len(workflows)}_{i}",
                        "author": self.rand.choice(reviewers) if reviewers else "reviewer1",
                        "text": f"Review comment {i+1} for {path.split('/')[-1]}",
                        "timestamp": self._iso_timestamp(),
                        "resolved": workflow_status == "reviewed" and i < num_comments - 1,
                    }
                    workflow["comments"].append(comment)
            
            # Add approvals
            if workflow_status == "reviewed":
                for reviewer in workflow["reviewers"]:
                    workflow["approvals"][reviewer] = {
                        "status": "approved" if self.rand.random() > 0.2 else "rejected",
                        "timestamp": self._iso_timestamp(),
                        "comment": "Approved" if self.rand.random() > 0.2 else "Needs revision",
                    }
            
            workflows.append(workflow)
        
        return {
            "workflows": workflows,
            "totalWorkflows": len(workflows),
            "workflowType": "review",
        }
    
    def generate_translation_workflow_data(
        self,
        content_paths: List[str],
        source_language: str = "en",
        target_languages: List[str] = None,
        workflow_status: str = "pending",
    ) -> Dict:
        """Generate translation workflow data."""
        if target_languages is None:
            target_languages = ["es", "fr", "de"]
        
        translation_jobs = []
        
        for path in content_paths:
            for target_lang in target_languages:
                job = {
                    "contentPath": path,
                    "sourceLanguage": source_language,
                    "targetLanguage": target_lang,
                    "workflowType": "translation",
                    "status": workflow_status,
                    "created": self._iso_timestamp(),
                    "createdBy": "admin",
                    "translationProvider": "aem-translation",
                    "dueDate": self._future_timestamp(days=14).isoformat(),
                    "wordCount": self.rand.randint(100, 1000),
                    "progress": 0 if workflow_status == "pending" else self.rand.randint(10, 100),
                    "translator": f"translator_{target_lang}" if workflow_status != "pending" else None,
                }
                
                translation_jobs.append(job)
        
        return {
            "translationJobs": translation_jobs,
            "totalJobs": len(translation_jobs),
            "sourceLanguage": source_language,
            "targetLanguages": target_languages,
        }
    
    def generate_approval_workflow_data(
        self,
        content_paths: List[str],
        approvers: List[str] = None,
        approval_levels: int = 2,
    ) -> Dict:
        """Generate approval workflow data."""
        if approvers is None:
            approvers = ["approver1", "approver2", "manager"]
        
        approvals = []
        
        for path in content_paths:
            approval = {
                "contentPath": path,
                "workflowType": "approval",
                "status": "pending",
                "created": self._iso_timestamp(),
                "approvalLevels": [],
            }
            
            # Generate approval levels
            for level in range(1, approval_levels + 1):
                level_data = {
                    "level": level,
                    "approver": approvers[min(level - 1, len(approvers) - 1)],
                    "status": "pending",
                    "required": True,
                    "comments": [],
                }
                
                # Randomly approve some levels
                if self.rand.random() > 0.5 and level > 1:
                    level_data["status"] = "approved"
                    level_data["approvedAt"] = self._iso_timestamp()
                
                approval["approvalLevels"].append(level_data)
            
            approvals.append(approval)
        
        return {
            "approvals": approvals,
            "totalApprovals": len(approvals),
            "approvalLevels": approval_levels,
        }
    
    def generate_workflow_metadata_file(
        self,
        base: str,
        review_data: Optional[Dict] = None,
        translation_data: Optional[Dict] = None,
        approval_data: Optional[Dict] = None,
    ) -> Tuple[str, bytes]:
        """Generate workflow metadata JSON file."""
        metadata = {
            "workflows": {},
            "lastUpdated": self._iso_timestamp(),
        }
        
        if review_data:
            metadata["workflows"]["review"] = review_data
        
        if translation_data:
            metadata["workflows"]["translation"] = translation_data
        
        if approval_data:
            metadata["workflows"]["approval"] = approval_data
        
        metadata_path = safe_join(base, "metadata", "workflow-states.json")
        metadata_bytes = json.dumps(metadata, indent=2).encode("utf-8")
        
        return metadata_path, metadata_bytes
    
    def _iso_timestamp(self) -> str:
        """Generate ISO timestamp."""
        return datetime.utcnow().isoformat() + "Z"
    
    def _future_timestamp(self, days: int = 7) -> datetime:
        """Generate future timestamp."""
        return datetime.utcnow() + timedelta(days=days)


def generate_workflow_enabled_dataset(
    config,
    base: str,
    content_paths: List[str],
    include_review: bool = True,
    include_translation: bool = True,
    include_approval: bool = True,
    reviewers: List[str] = None,
    target_languages: List[str] = None,
    rand=None,
) -> Dict[str, bytes]:
    """Generate workflow metadata for a dataset."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    generator = WorkflowDataGenerator(config, rand)
    files = {}
    
    review_data = None
    translation_data = None
    approval_data = None
    
    if include_review:
        review_data = generator.generate_review_workflow_data(
            content_paths,
            reviewers=reviewers,
            workflow_status="pending",
        )
    
    if include_translation:
        translation_data = generator.generate_translation_workflow_data(
            content_paths,
            target_languages=target_languages,
            workflow_status="pending",
        )
    
    if include_approval:
        approval_data = generator.generate_approval_workflow_data(
            content_paths,
            approvers=reviewers,
        )
    
    # Generate metadata file
    metadata_path, metadata_bytes = generator.generate_workflow_metadata_file(
        base,
        review_data=review_data,
        translation_data=translation_data,
        approval_data=approval_data,
    )
    
    files[metadata_path] = metadata_bytes
    
    return files
