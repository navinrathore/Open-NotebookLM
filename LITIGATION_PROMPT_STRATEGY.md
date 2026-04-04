# 🏛️ LawNidhi Litigation Prompt Strategy

This document serves as the persistent audit trail for our litigation-specific extraction requirements, few-shot examples, and general refinement notes.

## 🛠️ Extraction Requirements (Proposed)
| Target Field | Description | Importance |
| :----------- | :---------- | :--------- |
| **Petitioner** | The person or entity initiating the case (Applicant). | 🔴 High |
| **Respondent** | The person or entity against whom the case is filed. | 🔴 High |
| **Date of Order** | The specific date the order was passed or signed. | 🔴 High |
| **Next Hearing** | Any future date mentioned for the next session (List on...). | 🔴 High |
| **Court/Judge** | Coram details (Chairperson, Judicial/Expert Members). | 🔴 High |
| **Compliance** | Status of compliance by respondents for previous directions. | 🔴 High |
| **Action Items** | Specific action points / directions listed at the end of the order. | 🔴 High |
| **Responsibility** | Who is responsible for each action item (be specific). | 🔴 High |
| **Our Counsel** | Identification of 'Hemlata Singh' or team in the counsel block. | 🟡 Medium |
| **Case Status** | Adjourned, Disposed, Interim Order, etc. | 🟡 Medium |

## 🧪 Few-Shot Examples (Pending Documents)
> [!NOTE]
> Once sample documents are provided, we will populate this section with input (Order Snippet) and output (Extracted JSON/Text) pairs.

### Example 1: NGT Order (OA 985/2019)
**Input Context**:
```text
Original Application No. 985/2019 (I.A. No. 568/2024)
In Re: Water Pollution by Tanneries... vs CPCB & Ors.
Date of hearing: 01.07.2025
...
4. Reply on behalf of Principal Secretary, Environment... dated 17.03.2025 has been filed... 
reveals that adequate arrangement for supply of water... are not made. 
...
9. Officers of UP Jal Nigam, Jal Kal Department and Health Department will virtually remain present on the next date of hearing.
10. List on 27.05.2025.
Prakash Shrivastava, CP
```
**Desired Output**:
```json
{
  "case_id": "OA 985/2019",
  "petitioner": "In Re: Water Pollution by Tanneries at Jajmau Kanpur Uttar Pradesh",
  "respondent": "Central Pollution Control Board & Ors.",
  "court": "National Green Tribunal",
  "judge_coram": ["Justice Prakash Shrivastava, CP", "Justice Sudhir Agarwal, JM", "Dr. A. Senthil Vel, EM"],
  "order_date": "2025-04-08",
  "next_hearing": "2025-05-27",
  "compliance_summary": "Principal Secretary, Environment (UP) filed a reply on 17.03.2025 acknowledging that water supply arrangements (50 kld for 5000 people) are inadequate.",
  "action_items": [
    {
      "task": "Re-examine water supply in affected areas and file fresh report.",
      "responsible": "State of Uttar Pradesh / Learned AAG",
      "deadline": "2025-05-27"
    },
    {
      "task": "Examine reply and summarize lapses/lacunas.",
      "responsible": "Amicus Curiae (Ms. Katyayni)",
      "deadline": "2025-05-27"
    },
    {
      "task": "Virtual appearance on next date.",
      "responsible": ["UP Jal Nigam", "Jal Kal Department", "Health Department"],
      "deadline": "2025-05-27"
    }
  ],
  "counsel_match": null
}
```

### Example 2: NGT Order (Medical Assistance Directions)
**Input Context**:
```text
Original Application No. 985/2019
Date of hearing: 03.02.2026
...
6. Learned Amicus Curiae has referred to the list of the inhabitants... affected by the chromium and mercury...
The State is directed to respond to the above submission and disclose the treatment/facility/medical assistance 
which has been provided to these persons... Let this information be also disclosed in the next affidavit.
7. List on 07.04.2026.
Prakash Shrivastava, CP
```
**Desired Output**:
```json
{
  "case_id": "OA 985/2019",
  "petitioner": "In Re: Water Pollution by Tanneries at Jajmau Kanpur Uttar Pradesh",
  "respondent": "CPCB & Ors.",
  "court": "National Green Tribunal",
  "judge_coram": ["Justice Prakash Shrivastava, CP", "Dr. A. Senthil Vel, EM"],
  "order_date": "2026-02-03",
  "next_hearing": "2026-04-07",
  "compliance_summary": "Fresh reports filed by DMs and State of UP regarding previous recommendations.",
  "action_items": [
    {
      "task": "Respond and disclose treatment/facility/medical assistance provided to identified victims.",
      "responsible": "State of UP",
      "deadline": "2026-04-07"
    },
    {
      "task": "Prepare table disclosing if action taken is as per timeline and progress made.",
      "responsible": "Amicus Curiae (Ms. Katyayni)",
      "deadline": "2026-04-07"
    }
  ],
  "counsel_match": null
}
```

## 📈 Improvement Notes
*   **04-04-2026**: Strategy document initialized. Ready for Phase 2.
