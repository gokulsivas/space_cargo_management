import os
import csv
from datetime import datetime
import polars as pl
from typing import List, Dict, Optional

class UserTracker:
    def __init__(self, filename: str = "user_actions.csv"):
        self.filename = filename
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Ensure the user actions CSV file exists with proper headers."""
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'user_id',
                    'action_type',
                    'item_id',
                    'container_id',
                    'details'
                ])

    def log_action(self, user_id: str, action_type: str, 
                  item_id: Optional[str] = None, 
                  container_id: Optional[str] = None,
                  details: Optional[str] = None):
        """
        Log a user action to the CSV file.
        
        Args:
            user_id: ID of the user performing the action
            action_type: Type of action (e.g., 'retrieve', 'place', 'undock')
            item_id: ID of the item involved (if any)
            container_id: ID of the container involved (if any)
            details: Additional details about the action
        """
        try:
            with open(self.filename, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    user_id,
                    action_type,
                    item_id or '',
                    container_id or '',
                    details or ''
                ])
            return True
        except Exception as e:
            print(f"Error logging user action: {str(e)}")
            return False

    def get_user_actions(self, user_id: str) -> List[Dict]:
        """
        Get all actions performed by a specific user.
        
        Args:
            user_id: ID of the user to get actions for
            
        Returns:
            List of dictionaries containing user actions
        """
        try:
            df = pl.read_csv(self.filename)
            user_actions = df.filter(pl.col("user_id") == user_id).to_dicts()
            return user_actions
        except Exception as e:
            print(f"Error getting user actions: {str(e)}")
            return []

    def get_item_history(self, item_id: str) -> List[Dict]:
        """
        Get the history of actions performed on a specific item.
        
        Args:
            item_id: ID of the item to get history for
            
        Returns:
            List of dictionaries containing item history
        """
        try:
            df = pl.read_csv(self.filename)
            item_history = df.filter(pl.col("item_id") == item_id).to_dicts()
            return item_history
        except Exception as e:
            print(f"Error getting item history: {str(e)}")
            return []

    def get_container_history(self, container_id: str) -> List[Dict]:
        """
        Get the history of actions performed on a specific container.
        
        Args:
            container_id: ID of the container to get history for
            
        Returns:
            List of dictionaries containing container history
        """
        try:
            df = pl.read_csv(self.filename)
            container_history = df.filter(pl.col("container_id") == container_id).to_dicts()
            return container_history
        except Exception as e:
            print(f"Error getting container history: {str(e)}")
            return [] 