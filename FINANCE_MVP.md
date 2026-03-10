# Finance MVP: Automatic Fee Billing and Payment Deduction

This document describes the implemented MVP for automatic student fee billing and payment deduction in the School Management System.

## Overview

When a student is admitted or enrolled, the system automatically creates a fee invoice based on the school's fee structure. When a Finance Officer records a payment, the amount is deducted from the student's balance and reflected across all panels in real time.

---

## 1. Automatic Fee Billing on Student Admission/Enrollment

Fee invoices are created automatically in these flows:

| Flow | Location | Auto-billing |
|------|----------|--------------|
| **Add Student** | `add_student` (HOD) | ✓ Creates `FeeBalance` after enrollment |
| **Single Enrollment** | `add_enrollment` | ✓ Creates `FeeBalance` for class + session |
| **Bulk Enrollment** | `bulk_enrollment` | ✓ Creates `FeeBalance` for each enrolled student |
| **Transfer Student** | `transfer_student` | ✓ Updates `FeeBalance` with new class fee structure |
| **Bulk Promotion** | `bulk_promotion` | ✓ Creates `FeeBalance` for new session/class |

### Flow

1. Student is admitted or enrolled in a class.
2. System identifies the student's class and session.
3. System retrieves the fee structure for that class and session.
4. System creates or updates a `FeeBalance` record.

### Example

- **Student:** Abdulmalik Duale  
- **Class:** Grade 8  
- **Term:** Term 1  
- **Total Fee:** KES 15,000  
- **Amount Paid:** KES 0  
- **Balance:** KES 15,000  
- **Status:** Pending  

---

## 2. Fee Structure Setup (Admin Panel)

School Admin defines fee structures per class and term:

- **Class:** Grade 7  
- **Term:** Term 1  
- **Tuition:** KES 10,000  
- **Transport:** KES 2,000  
- **Lunch:** KES 3,000  
- **Total Fee:** KES 15,000  

When a student joins Grade 7, the system assigns this fee structure automatically.

---

## 3. Finance Officer Payment Entry

Finance Officer records payments via the fee collection form:

- Student
- Amount Paid
- Payment Method (M-Pesa, Cash, Bank, etc.)
- Receipt Number
- Date

**Logic:** `New Balance = Total Fee - Total Paid`

---

## 4. Automatic Balance Update Across Panels

After a payment is recorded:

| Panel | What is shown |
|-------|----------------|
| **Finance Panel** | Payment history, balance, reports |
| **Student Panel** | My Fees: Total, Paid, Balance |
| **Parent Panel** | Child fees: Total, Paid, Balance |

All panels use `FeeBalance` as the single source of truth.

---

## 5. Payment History

All payments are stored in `FeePayment` with:

- Date
- Amount
- Method
- Receipt number
- Transaction reference

---

## 6. Automatic Fee Status

Status is derived from balance:

| Condition | Status |
|-----------|--------|
| Balance = 0 | Paid |
| Balance > 0 | Partial |
| Paid = 0 | Unpaid |

---

## 7. Fee Notifications (Optional)

When a payment is recorded:

- SMS receipt can be sent (if SMS is configured)
- Parent notification is created

---

## 8. Multi-School SaaS Isolation

All financial records are scoped by `school_id`:

- `FeeBalance`, `FeePayment`, `FeeStructure` are filtered by school
- School A cannot access School B's data

---

## 9. Receipt Generation

After payment, a PDF receipt can be generated with:

- School logo (if configured)
- Student name
- Admission number
- Amount paid
- Balance after payment
- Payment method
- Receipt number
- Date
- Finance Officer (Received By)

---

## 10. Security Rules

| Role | Permissions |
|------|-------------|
| Finance Officer / School Admin | Record payments, modify fee records, delete payment records |
| Students / Parents | View fee information only |

---

## Key Models

- **FeeBalance** – Per-student, per-session fee totals and balance
- **FeePayment** – Individual payment transactions
- **FeeStructure** – Fee structure per class and session
- **FeeGroup** / **FeeGroupItem** – Fee components (tuition, transport, etc.)

---

## Key Views

| View | Purpose |
|------|---------|
| `fee_collection` | Record payments |
| `print_fee_receipt` | Generate PDF receipt |
| `finance_student_billing` | View/manage student billing |
| `student_view_fees` | Student portal fees |
| `parent_view_child_fees` | Parent portal child fees |

---

## Manual Invoice Generation

If needed, Finance Officer can generate/update invoices for all enrolled students:

- **Finance Panel → Student Billing → Generate Invoices**

This creates or updates `FeeBalance` records for students who have a class and session but no fee record.
