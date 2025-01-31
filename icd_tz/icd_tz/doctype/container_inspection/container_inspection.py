# Copyright (c) 2024, elius mgani and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import nowdate
from frappe.model.document import Document
from icd_tz.icd_tz.api.utils import validate_cf_agent, validate_draft_doc

class ContainerInspection(Document):
    def before_insert(self):
        self.get_custom_verification_services()
    
    def after_insert(self):
        self.update_in_yard_booking()
        frappe.db.set_value(
            "Container",
            self.container_id,
            "status",
            "At Inspection"
        )
    
    def before_save(self):
        if not self.company:
            self.company = frappe.defaults.get_user_default("Company")
    
    def validate(self):
        validate_draft_doc("In Yard Container Booking", self.in_yard_container_booking)
        validate_cf_agent(self)
    
    def on_submit(self):
        self.update_container_doc()
    
    def update_in_yard_booking(self):
        if not self.in_yard_container_booking:
            return
        
        frappe.db.set_value(
            "In Yard Container Booking",
            self.in_yard_container_booking,
            "container_inspection",
            self.name
        )
    
    def update_container_doc(self):
        if not self.container_id:
            return
        
        container_doc = frappe.get_doc("Container", self.container_id)
        if self.new_container_location:
            container_doc.current_location = self.new_container_location
        
        for row in self.services:
            if row.status_changed_to and row.status_changed_to != container_doc.freight_indicator:
                container_doc.freight_indicator = row.status_changed_to
        
        container_doc.last_inspection_date = nowdate()
        container_doc.save(ignore_permissions=True)

    @frappe.whitelist()
    def get_custom_verification_services(self, caller=None):
        if caller == "Front End" and isinstance(self, str):
            self = frappe.parse_json(self)
        
        if not self.get("in_yard_container_booking"):
            return
        
        has_custom_verification_charges = frappe.db.get_value(
			"In Yard Container Booking",
            self.get("in_yard_container_booking"),
            "has_custom_verification_charges"
		)

        if has_custom_verification_charges == "Yes":
            verification_item = frappe.db.get_single_value("ICD TZ Settings", "custom_verification_item")
            if not verification_item:
                frappe.throw("Custom Verification item is not set in ICD TZ Settings, Please set it to continue")
            
            service_names = [row.get("service") for row in self.get("services")]
            if verification_item not in service_names:
                if caller == "Front End":
                    return verification_item
                else:
                    self.append("services", {
                        "service": verification_item
                    })


@frappe.whitelist()
def create_bulk_inspections(data):
    data = frappe.parse_json(data)
    bookings = frappe.db.get_all(
		"In Yard Container Booking",
		filters={
            "docstatus": 1,
			"m_bl_no": data.get("m_bl_no"),
            "container_inspection": ("is", "not set")
		},
        fields=["name", "container_id", "inspection_datetime"]
	)
    if len(bookings) == 0:
        frappe.msgprint(f"No submitted Container Bookings found for M BL No: <b>{data.get('m_bl_no')}</b>")
        return
    
    count = 0
    for booking in bookings:
        doc = frappe.new_doc("Container Inspection")
        doc.in_yard_container_booking = booking.name
        doc.container_id = booking.container_id
        doc.inspector_name = data.get("inspector_name")
        doc.inspection_date = booking.inspection_datetime
        
        doc.flags.ignore_permissions = True
        doc.insert()
        doc.reload()

        if doc.get("name"):
            count += 1

    return count