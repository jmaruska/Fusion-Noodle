"""
Data integrity utilities for robust validation and composability.
Implements the enhanced data integrity specifications.
"""

from typing import Dict, Any, List, Tuple, Optional, Callable

class DataIntegrityValidator:
    """Enhanced data validation implementing robust composability rules"""
    
    @staticmethod
    def validate_data_flow_composition(
        input_data: Dict[str, Any], 
        node_type: str,
        logger_func: Optional[Callable] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate data flow composition according to specification.
        Ensures intelligent data compounding from any source in any order.
        """
        errors = []
        
        try:
            # Cross-type compatibility validation
            if 'collection' in input_data and 'transform' in input_data:
                collection_valid, collection_errors = DataIntegrityValidator._validate_collection_transform_compatibility(
                    input_data['collection'], input_data['transform']
                )
                errors.extend(collection_errors)
                
            # Semantic consistency validation
            semantic_valid, semantic_errors = DataIntegrityValidator._validate_semantic_consistency(
                input_data, node_type
            )
            errors.extend(semantic_errors)
            
            if logger_func:
                logger_func(f"Data flow composition validation for {node_type}: {len(errors)} errors found")
                
            return len(errors) == 0, errors
            
        except Exception as e:
            error_msg = f"Data flow composition validation failed: {str(e)}"
            if logger_func:
                logger_func(error_msg)
            return False, [error_msg]
    
    @staticmethod
    def _validate_collection_transform_compatibility(
        collection_data: Any, 
        transform_data: Any
    ) -> Tuple[bool, List[str]]:
        """Validate transform chains are compatible with collections"""
        errors = []
        
        try:
            # Ensure collection is valid
            if isinstance(collection_data, dict):
                if 'instances' not in collection_data:
                    errors.append("Collection missing instances array")
                elif not isinstance(collection_data['instances'], list):
                    errors.append("Collection instances must be list")
                    
            # Ensure transform is valid
            if transform_data is not None:
                if not isinstance(transform_data, dict):
                    errors.append("Transform must be dictionary or None")
                else:
                    # Validate transform format compatibility
                    if not any(key in transform_data for key in ['tx', 'translation', 'transform_matrix', 'transform_type']):
                        errors.append("Transform missing required format fields")
                        
        except Exception as e:
            errors.append(f"Collection-transform compatibility validation failed: {str(e)}")
            
        return len(errors) == 0, errors
    
    @staticmethod
    def _validate_semantic_consistency(
        input_data: Dict[str, Any], 
        node_type: str
    ) -> Tuple[bool, List[str]]:
        """Validate logical consistency beyond type checking"""
        errors = []
        
        try:
            # Mathematical consistency rules  
            if 'transform' in input_data and input_data['transform']:
                transform = input_data['transform']
                if isinstance(transform, dict):
                    # Check for reasonable scale values
                    for scale_key in ['sx', 'sy', 'sz']:
                        if scale_key in transform:
                            scale_val = transform[scale_key]
                            if isinstance(scale_val, (int, float)):
                                if scale_val <= 0:
                                    errors.append(f"Scale {scale_key}={scale_val} must be positive")
                                elif scale_val > 1000:
                                    errors.append(f"Scale {scale_key}={scale_val} exceeds reasonable limit (1000)")
                                    
        except Exception as e:
            errors.append(f"Semantic consistency validation failed: {str(e)}")
            
        return len(errors) == 0, errors
    
class RuntimeIntegrityChecker:
    """Continuous runtime validation during execution"""
    
    @staticmethod
    def validate_node_execution(
        node_type: str,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        logger_func: Optional[Callable] = None
    ) -> Tuple[bool, List[str]]:
        """Comprehensive validation of node execution"""
        errors = []
        
        try:
            # Post-execution validation  
            post_valid, post_errors = RuntimeIntegrityChecker._validate_post_execution(
                node_type, outputs
            )
            errors.extend(post_errors)
            
            return len(errors) == 0, errors
            
        except Exception as e:
            error_msg = f"Runtime integrity validation failed: {str(e)}"
            if logger_func:
                logger_func(error_msg)
            return False, [error_msg]
    
    @staticmethod
    def _validate_post_execution(
        node_type: str,
        outputs: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """Validate outputs after node execution"""
        errors = []
        
        # Validate outputs are properly formatted
        for key, value in outputs.items():
            if value is None:
                errors.append(f"Output '{key}' cannot be None")
            elif hasattr(value, '__dict__'):
                # Allow CollectionSpec objects as per specification v2 update
                if hasattr(value, 'to_dict') and not hasattr(value, 'collection_type'):
                    errors.append(f"Output '{key}' is contract object, should be serialized via .to_dict()")
                    
        return len(errors) == 0, errors
