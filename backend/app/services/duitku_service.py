"""
Duitku Payment Gateway Service
"""
import hashlib
import json
from typing import Optional, Dict, Any
import requests

from app.core.config import get_settings

settings = get_settings()


class DuitkuService:
    """Duitku payment gateway integration."""
    
    def __init__(self):
        self.merchant_code = settings.DUITKU_MERCHANT_CODE
        self.api_key = settings.DUITKU_API_KEY
        self.callback_url = settings.DUITKU_CALLBACK_URL
        self.return_url = settings.DUITKU_RETURN_URL
        self.sandbox = settings.DUITKU_SANDBOX
        self.base_url = "https://sandbox.duitku.com" if self.sandbox else "https://passport.duitku.com"
    
    def create_payment(
        self,
        order_id: str,
        amount: int,
        payment_method: Optional[str] = None,
        product_details: str = "Clipzi AI Credits",
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a Duitku payment request."""
        signature = self._generate_signature(order_id, amount)
        
        payload = {
            "merchantCode": self.merchant_code,
            "amount": str(amount),
            "merchantOrderId": order_id,
            "productDetails": product_details,
            "signature": signature,
            "callbackUrl": self.callback_url,
            "returnUrl": self.return_url,
        }
        
        if payment_method:
            payload["paymentMethod"] = payment_method
        if customer_email:
            payload["customerEmail"] = customer_email
        if customer_phone:
            payload["customerPhone"] = customer_phone
        
        # In production, POST to Duitku API
        # For now, return mock payment URL
        payment_url = f"{self.base_url}/webview/payment/{order_id}"
        
        return {
            "payment_url": payment_url,
            "transaction_id": order_id,
            "status": "pending",
        }
    
    def _generate_signature(self, order_id: str, amount: int) -> str:
        """Generate Duitku payment signature."""
        signature_string = f"{self.merchant_code}{order_id}{amount}{self.api_key}"
        return hashlib.sha256(signature_string.encode()).hexdigest()
    
    def verify_callback_signature(
        self,
        merchant_code: str,
        payment_amount: str,
        transaction_id: str,
        result_code: str,
        status: str,
        signature: str,
    ) -> bool:
        """Verify Duitku callback signature."""
        signature_string = f"{merchant_code}{payment_amount}{transaction_id}{result_code}{status}{self.api_key}"
        expected = hashlib.sha256(signature_string.encode()).hexdigest()
        return signature == expected
    
    def verify_webhook_signature(
        self,
        merchant_code: str,
        payment_amount: str,
        transaction_id: str,
        result_code: str,
        status: str,
        signature: str,
    ) -> bool:
        """Verify Duitku webhook signature."""
        return self.verify_callback_signature(
            merchant_code, payment_amount, transaction_id, result_code, status, signature
        )