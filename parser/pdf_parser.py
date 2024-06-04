from __future__ import annotations
from pydantic import BaseModel, ValidationError
from typing import Union, Any, Optional, Dict, Tuple, List, NewType
import json
import asyncio
import base64
from fastapi import UploadFile
import fitz
import re
import uuid
from collections import Counter, defaultdict
from thefuzz import process  
import llm, prompts, utils
from parser.base_parser import BaseParser

JSONstr = NewType('JSONstr', str)

class TableOfContentsChild(BaseModel):
    number: str
    title: str

class TableOfContents(BaseModel):
    section: Optional[str]
    number: str
    title: str
    children: Optional[List[Union[TableOfContents, TableOfContentsChild]]]

    def find_child(self, section: Optional[str], number: str) -> Optional[Union[TableOfContents, TableOfContentsChild]]:
        """find an existing child by section and number."""
        if not self.children:
            return None
        for child in self.children:
            if isinstance(child, TableOfContents) and child.section == section and child.number == number:
                return child
            if isinstance(child, TableOfContentsChild) and child.number == number:
                return child
        return None

    def add_child(self, child: Union[TableOfContents, TableOfContentsChild]):
        """add a new child or merge with an existing one."""
        if not self.children:
            self.children = []

        if isinstance(child, TableOfContents):
            existing_child = self.find_child(child.section, child.number)
            if existing_child and isinstance(existing_child, TableOfContents):
                existing_child.children = merge_children(existing_child.children, child.children or [])
            else:
                self.children.append(child)
        else:
            if not any(isinstance(existing, TableOfContentsChild) and existing.number == child.number for existing in self.children):
                self.children.append(child)


class Contents(BaseModel):
    level: JSONstr
    sublevel: JSONstr | str
    subsublevel: JSONstr | str
    toc: List[Union[TableOfContents, TableOfContentsChild]]


class TableOfContentsDict(BaseModel):
    contents: List[Contents]

def merge_children(existing_children: Optional[List[Union[TableOfContents, TableOfContentsChild]]], new_children: List[Union[TableOfContents, TableOfContentsChild]]) -> List[Union[TableOfContents, TableOfContentsChild]]:
    """merge a list of new children into existing children."""
    if existing_children is None:
        existing_children = []

    existing_dict = {child.number: child for child in existing_children if isinstance(child, TableOfContents)}

    for new_child in new_children:
        if isinstance(new_child, TableOfContents):
            if new_child.number in existing_dict:
                existing_child = existing_dict[new_child.number]
                existing_child.children = merge_children(existing_child.children, new_child.children or [])
            else:
                existing_children.append(new_child)
        else:
            if not any(isinstance(child, TableOfContentsChild) and child.number == new_child.number for child in existing_children):
                existing_children.append(new_child)

    return existing_children

class PDFParser(BaseParser):
    """
    Parses a PDF that contains a Table of Contents (ToC) and extracts structured content to a dict.
    Absolutely hinders on the ToC and Markdown formatting of the toc.
    """
    
    def __init__(self, rate_limit: int = 50):
        super().__init__(rate_limit)
        self.document = None
        self.toc_pages = None
        self.toc_md_string = None
        self.content_md_string = None
        self.toc_hierarchy_schema = None
        self.adjusted_toc_hierarchy_schema = None
        self.master_toc = None
        self.no_md_flag = False

    async def load_document(self, file: Union[UploadFile, str]) -> None:
        """
        Load a PDF document from an uploaded file or a file path.
        """
        if isinstance(file, UploadFile):
            file_content = await file.read()
            self.document = fitz.open(stream=file_content, filetype="pdf")
        elif isinstance(file, str):
            self.document = fitz.open(file)
        else:
            raise ValueError("file must be an instance of UploadFile or str.")
        self.toc_md_string, self.content_md_string = await self.generate_md_string()
        # self.toc_md_string_lines = self.toc_md_string.split("\n").lower()
        # self.content_md_string_lines = self.content_md_string.split("\n").lower()
        #self.toc_hierarchy_schema = await self.generate_toc_hierarchy_schema()
        # with open("zztoc_md_string.md", "w") as f:
        #     f.write(self.toc_md_string) 
        # with open("zzcontent_md_string.md", "w") as f:
        #     f.write(self.content_md_string)
        self.no_md_flag = True
        self.toc_hierarchy_schema = {
            "Part": "#",
            "Schedule": "#",
            "Chapter": "##",
            "General supplementary provisions": "##",
            "Final provisions": "##",
            "Northern ireland": "##",
            "General": "###",
            "Companies and Companies Acts": "###",
            "Types of company": "###",
            "Requirements for registration": "###",
            "Registration and its effect": "###",
            "Introductory": "###",
            "Articles of association": "###",
            "Alteration of articles": "###",
            "Supplementary": "###",
            "Resolutions and agreements affecting a company\u2019s constitution": "###",
            "Miscellaneous and supplementary provisions": "###",
            "Companies and companies acts": "###",
            "Other provisions with respect to a company\u2019s constitution": "###",
            "Supplementary provisions": "###",
            "Capacity of company and power of directors to bind it": "###",
            "Formalities of doing business under the law of england and wales or northern ireland": "###",
            "Formalities of doing business under the law of scotland": "###",
            "Other matters": "###",
            "Prohibited names": "###",
            "Sensitive words and expressions": "###",
            "Permitted characters etc": "###",
            "Indications of company type or legal form": "###",
            "Similarity to other names": "###",
            "Other powers of the secretary of state": "###",
            "Welsh companies": "###",
            "Private company becoming public": "###",
            "Public company becoming private": "###",
            "Special cases": "###",
            "General prohibition": "###",
            "Subsidiary acting as personal representative or trustee": "###",
            "Subsidiary acting as dealer in securities": "###",
            "Exercise of members\u2019 rights": "###",
            "A company\u2019s directors": "###",
            "Removal": "###",
            "The general duties": "###",
            "Declaration of interest in existing transaction or arrangement": "###",
            "Transactions with directors requiring approval of members": "###",
            "Loans, quasi-loans and credit transactions": "###",
            "Payments for loss of office": "###",
            "Provision protecting directors from liability": "###",
            "Ratification of acts giving rise to liability": "###",
            "Provision for employees on cessation or transfer of business": "###",
            "Records of meetings of directors": "###",
            "Meaning of \"director\" and \"shadow director\"": "###",
            "Other definitions": "###",
            "Private companies": "###",
            "Public companies": "###",
            "Provisions applying to private companies with a secretary and to public companies": "###",
            "General provisions about written resolutions": "###",
            "Circulation of written resolutions": "###",
            "Agreeing to written resolutions": "###",
            "Resolutions at meetings": "###",
            "Adjourned meetings": "###",
            "Electronic communications": "###",
            "Application to class meetings": "###",
            "Public companies: additional requirements for agms": "###",
            "Additional requirements for quoted companies": "###",
            "Website publication of poll results": "###",
            "Independent report on poll": "###",
            "Donations and expenditure to which this part applies": "###",
            "Authorisation required for donations or expenditure": "###",
            "Remedies in case of unauthorised donations or expenditure": "###",
            "Exemptions": "###",
            "Companies subject to the small companies regime": "###",
            "Quoted and unquoted companies": "###",
            "Individual accounts": "###",
            "Group accounts: small companies": "###",
            "Group accounts: other companies": "###",
            "Group accounts: general": "###",
            "Information to be given in notes to the accounts": "###",
            "Approval and signing of accounts": "###",
            "Directors\u2019 report": "###",
            "Quoted companies: directors\u2019 remuneration report": "###",
            "Duty to circulate copies of accounts and reports": "###",
            "Option to provide summary financial statement": "###",
            "Quoted companies: requirements as to website publication": "###",
            "Right of member or debenture holder to demand copies of accounts and reports": "###",
            "Requirements in connection with publication of accounts and reports": "###",
            "Public companies: laying of accounts and reports before general meeting": "###",
            "Duty to file accounts and reports": "###",
            "Filing obligations of different descriptions of company": "###",
            "Requirements where abbreviated accounts delivered": "###",
            "Failure to file accounts and reports": "###",
            "Voluntary revision": "###",
            "Secretary of state\u2019s notice": "###",
            "Application to court": "###",
            "Power of authorised person to require documents etc": "###",
            "Liability for false or misleading statements in reports": "###",
            "Accounting and reporting standards": "###",
            "Companies qualifying as medium-sized": "###",
            "General power to make further provision about accounts and reports": "###",
            "Other supplementary provisions": "###",
            "Requirement for audited accounts": "###",
            "Exemption from audit: small companies": "###",
            "Exemption from audit: dormant companies": "###",
            "Companies subject to public sector audit": "###",
            "General power of amendment by regulations": "###",
            "General provisions": "###",
            "Auditor\u2019s report": "###",
            "Duties and rights of auditors": "###",
            "Signature of auditor\u2019s report": "###",
            "Offences in connection with auditor\u2019s report": "###",
            "Removal of auditor": "###",
            "Failure to re-appoint auditor": "###",
            "Resignation of auditor": "###",
            "Statement by auditor on ceasing to hold office": "###",
            "Voidness of provisions protecting auditors from liability": "###",
            "Indemnity for costs of defending proceedings": "###",
            "Liability limitation agreements": "###",
            "Shares": "###",
            "Share capital": "###",
            "Power of directors to allot shares": "###",
            "Prohibition of commissions, discounts and allowances": "###",
            "Registration of allotment": "###",
            "Return of allotment": "###",
            "Existing shareholders\u2019 right of pre-emption": "###",
            "Exceptions to right of pre-emption": "###",
            "Exclusion of right of pre-emption": "###",
            "Disapplication of pre-emption rights": "###",
            "General rules": "###",
            "Additional rules for public companies": "###",
            "Non-cash consideration for shares": "###",
            "Transfer of non-cash asset in initial period": "###",
            "The share premium account": "###",
            "Relief from requirements as to share premiums": "###",
            "How share capital may be altered": "###",
            "Subdivision or consolidation of shares": "###",
            "Reconversion of stock into shares": "###",
            "Redenomination of share capital": "###",
            "Variation of class rights": "###",
            "Matters to be notified to the registrar": "###",
            "Private companies: reduction of capital supported by solvency statement": "###",
            "Reduction of capital confirmed by the court": "###",
            "Public company reducing capital below authorised minimum": "###",
            "Effect of reduction of capital": "###",
            "Exceptions from prohibition": "###",
            "Authority for purchase of own shares": "###",
            "Authority for off-market purchase": "###",
            "Authority for market purchase": "###",
            "The permissible capital payment": "###",
            "Requirements for payment out of capital": "###",
            "Objection to payment by members or creditors": "###",
            "Treasury shares": "###",
            "Register of debenture holders": "###",
            "Share certificates": "###",
            "Issue of certificates etc on allotment": "###",
            "Transfer of securities": "###",
            "Issue of certificates etc on transfer": "###",
            "Issue of certificates etc on allotment or transfer to financial institution": "###",
            "Share warrants": "###",
            "Powers exercisable": "###",
            "Notice requiring information about interests in shares": "###",
            "Orders imposing restrictions on shares": "###",
            "Power of members to require company to act": "###",
            "Register of interests disclosed": "###",
            "Meaning of interest in shares": "###",
            "Distributions by investment companies": "###",
            "Justification of distribution by reference to accounts": "###",
            "Requirements applicable in relation to relevant accounts": "###",
            "Application of provisions to successive distributions etc": "###",
            "Accounting matters": "###",
            "Distributions in kind": "###",
            "Consequences of unlawful distribution": "###",
            "Requirement to register company charges": "###",
            "Special rules about debentures": "###",
            "Charges in other jurisdictions": "###",
            "Orders charging land: northern ireland": "###",
            "The register of charges": "###",
            "Avoidance of certain charges": "###",
            "Companies\u2019 records and registers": "###",
            "Charges requiring registration": "###",
            "Charges on property outside the united kingdom": "###",
            "Powers of the secretary of state": "###",
            "Arrangements and reconstructions": "###",
            "Mergers and divisions of public companies": "###",
            "Requirements applicable to merger": "###",
            "Exceptions where shares of transferor company held by transferee company": "###",
            "Other exceptions": "###",
            "Requirements to be complied with in case of division": "###",
            "Expert\u2019s report and related matters": "###",
            "Powers of the court": "###",
            "Liability of transferee companies": "###",
            "Interpretation": "###",
            "The panel and its rules": "###",
            "Information": "###",
            "Co-operation": "###",
            "Hearings and appeals": "###",
            "Contravention of rules etc": "###",
            "Funding": "###",
            "Miscellaneous and supplementary": "###",
            "Opting in and opting out": "###",
            "Consequences of opting in": "###",
            "Takeover offers": "###",
            "Squeeze-out": "###",
            "Sell-out": "###",
            "Main provisions": "###",
            "Registrar\u2019s power to strike off defunct company": "###",
            "Voluntary striking off": "###",
            "Property vesting as bona vacantia": "###",
            "General effect of disclaimer": "###",
            "Disclaimer of leaseholds": "###",
            "Power of court to make vesting order": "###",
            "Protection of persons holding under a lease": "###",
            "Land subject to rentcharge": "###",
            "Effect of crown disclaimer: england and wales and northern ireland": "###",
            "Effect of crown disclaimer: scotland": "###",
            "Liability for rentcharge on company\u2019s land after dissolution": "###",
            "Administrative restoration to the register": "###",
            "Restoration to the register by the court": "###",
            "Powers of secretary of state to give directions to inspectors": "###",
            "Resignation, removal and replacement of inspectors": "###",
            "Power to obtain information from former inspectors etc": "###",
            "Power to require production of documents": "###",
            "Disqualification orders: consequential amendments": "###",
            "Registration of particulars": "###",
            "Other requirements": "###",
            "The registrar": "###",
            "Certificates of incorporation": "###",
            "Registered numbers": "###",
            "Delivery of documents to the registrar": "###",
            "Requirements for proper delivery": "###",
            "Public notice of receipt of certain documents": "###",
            "The register": "###",
            "Inspection etc of the register": "###",
            "Correction or removal of material on the register": "###",
            "The registrar\u2019s index of company names": "###",
            "Language requirements: translation": "###",
            "Language requirements: transliteration": "###",
            "Offences under the companies act": "###",
            "Production and inspection of documents": "###",
            "Company records": "###",
            "Service addresses": "###",
            "Sending or supplying documents or information": "###",
            "Requirements as to independent valuation": "###",
            "Notice of appointment of certain officers": "###",
            "Courts and legal proceedings": "###",
            "Meaning of \"uk-registered company\"": "###",
            "Meaning of \"subsidiary\" and related expressions": "###",
            "Meaning of \"undertaking\" and related expressions": "###",
            "Power to disqualify": "###",
            "Power to make persons liable for company\u2019s debts": "###",
            "Power to require statements to be sent to the registrar of companies": "###",
            "Sensitive words or expressions": "###",
            "Misleading names": "###",
            "Disclosure requirements": "###",
            "Consequences of failure to make required disclosure": "###",
            "Individuals and firms": "###",
            "Auditors general": "###",
            "The register of auditors": "###",
            "Information to be made available to public": "###",
            "Duties": "###",
            "Power to require second company audit": "###",
            "False and misleading statements": "###",
            "Fees": "###",
            "Delegation of secretary of state\u2019s functions": "###",
            "International obligations": "###",
            "General provision relating to offences": "###",
            "Notices etc": "###",
            "Miscellaneous and general": "###",
            "Transparency obligations": "###",
            "Regulation of actuaries etc": "###",
            "Information as to exercise of voting rights by institutional investors": "###",
            "Regulations and orders": "###",
            "Meaning of \"enactment\"": "###",
            "Consequential and transitional provisions": "###",
            "Disclosure of information under the enterprise act": "###",
            "Expenses of winding up": "###",
            "Commonhold associations": "###",
            "Statement of company\u2019s objects": "####",
            "Required indications for limited companies": "####",
            "Inappropriate use of indications of company type or legal form": "####",
            "Similarity to other name on registrar\u2019s index": "####",
            "Similarity to other name in which person has goodwill": "####",
            "Effect of provisions in company\u2019s articles": "####",
            "Information rights": "####",
            "Exercise of rights where shares held on behalf of others": "####",
            "Appointment and removal of directors": "####",
            "Service contracts": "####",
            "Substantial property transactions": "####",
            "General provisions about resolutions at meetings": "####",
            "Calling meetings": "####",
            "Notice of meetings": "####",
            "Members\u2019 statements": "####",
            "Procedure at meetings": "####",
            "Proxies": "####",
            "Shares held by company\u2019s nominee": "####",
            "Shares held by or for public company": "####",
            "Charges of public company on own shares": "####",
            "Circumstances in which financial assistance prohibited": "####",
            "Application of this part": "####",
            "Meeting of creditors or members": "####",
            "Court sanction for compromise or arrangement": "####",
            "Reconstructions and amalgamations": "####",
            "Obligations of company with respect to articles etc": "####",
            "Application for administrative restoration to the register": "####",
            "Requirements for administrative restoration": "####",
            "Application to be accompanied by statement of compliance": "####",
            "Registrar\u2019s decision on application for administrative restoration": "####",
            "Effect of administrative restoration": "####",
            "Application to court for restoration to the register": "####",
            "When application to the court may be made": "####",
            "Decision on application for restoration by the court": "####",
            "Effect of court order for restoration to the register": "####",
            "Company\u2019s name on restoration": "####",
            "Effect of restoration to the register where property has vested as bona vacantia": "####",
            "Eligibility for appointment": "####",
            "Independence requirement": "####",
            "Effect of appointment of a partnership": "####",
            "Supervisory bodies": "####",
            "Professional qualifications": "####",
            "Enforcement": "####",
            "Conduct of audits": "####",
            "The independent supervisor": "####",
            "Supervision of auditors general": "####",
            "Reporting requirement": "####",
            "Proceedings": "####",
            "Grants": "####",
            "Requirement to have directors": "#####",
            "Appointment": "#####",
            "Register of directors, etc": "#####"
        }

    def encode_page_as_base64(self, page: fitz.Page):
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        return base64.b64encode(pix.tobytes()).decode('utf-8')
    
    async def find_toc_pages(self) -> List[int]:
        """
        Find the ToC pages in the document.
        """
        # vol9
        #return [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31]
        # uk companies act
        return [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58]
        def encode_page_as_base64(page: fitz.Page):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            return base64.b64encode(pix.tobytes()).decode('utf-8')
        
        async def verify_toc_page(page: fitz.Page) -> bool:
            nonlocal checked_pages
            if page.number in checked_pages:
                utils.print_coloured(checked_pages[page.number], "cyan")
                return checked_pages[page.number]
            while True:
                messages=[
                    {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Is this page a Table of Contents? If there are no page numbers it is most likely not. Respond with ONLY 'yes' or 'no'"},
                        {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{encode_page_as_base64(page)}",
                        },
                        },
                    ],
                    }
                ]
                response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o", response_format="text")
                message_content = response.choices[0].message.content
                if message_content.lower() == "yes" or "yes" in message_content.lower():
                    utils.print_coloured(message_content, "green")
                    checked_pages[page.number] = True
                    return True
                elif message_content.lower() == "no" or "no" in message_content.lower():
                    utils.print_coloured(message_content, "red")
                    checked_pages[page.number] = False
                    return False
                
        toc_pages = []
        i = 0
        check_right = True 
        #for i in range(self.document.page_count):
        while i < self.document.page_count - 1:
            page = self.document[i]
            page_rect = page.rect
            if check_right:
                rect = fitz.Rect(page_rect.width * 0.7, 0, page_rect.width, page_rect.height)
            else:
                rect = fitz.Rect(0, 0, page_rect.width * 0.3, page_rect.height)
            words = page.get_text("words", clip=rect)
            words = [w for w in words if fitz.Rect(w[:4]) in rect]
            page_num_count = sum(1 for w in words if w[4].isdigit())
            percentage = page_num_count / len(words) if len(words) > 0 else 0
            i += 1
            if percentage > 0.4:
                toc_pages.append(i)
            # logic for silly LHS page numbers
            if i == 30 and check_right:
                if not toc_pages:
                    check_right = False
                    i = 0
        if not toc_pages:
            raise ValueError("No Table of Contents found - can not proceed.")
        utils.print_coloured(f"Potential ToC pages: {toc_pages}", "yellow")
        # verify the first and last pages
        start_index = 0
        end_index = len(toc_pages) - 1
        start_count = end_count = 0
        start_found = end_found = False
        checked_pages: Dict[int, bool] = {} 
        while start_index <= end_index:
            if start_found and end_found:
                break
            tasks = []
            if not start_found:
                utils.print_coloured(f"Is {toc_pages[start_index] - start_count} a Toc page?", "yellow")
                tasks.append(self.rate_limited_process(verify_toc_page, self.document[toc_pages[start_index] - start_count]))
            if not end_found:
                utils.print_coloured(f"Is {toc_pages[end_index] + end_count} a ToC page?", "yellow")
                tasks.append(self.rate_limited_process(verify_toc_page, self.document[toc_pages[end_index] + end_count]))
            
            results = await asyncio.gather(*tasks)
            if not start_found:
                start_result = results[0]
                if start_result:
                    if toc_pages[start_index] == 0 or toc_pages[start_index] - start_count == 0:
                        start_found = True
                    else:
                        utils.print_coloured(f"Is {toc_pages[start_index] - start_count - 1} a ToC page?", "yellow")
                        prev_page_result = await self.rate_limited_process(verify_toc_page, self.document[toc_pages[start_index] - start_count - 1])
                    if prev_page_result:
                        start_count += 1
                    else:
                        start_found = True
                else:
                    start_index += 1

            if not end_found:
                end_result = results[-1]
                if end_result:
                    utils.print_coloured(f"Is {toc_pages[end_index] + end_count + 1} a ToC page?", "yellow")
                    next_page_result = await self.rate_limited_process(verify_toc_page, self.document[toc_pages[end_index] + end_count + 1])
                    if next_page_result:
                        end_count += 1
                    else:
                        end_found = True
                else:
                    end_index -= 1
                
                if start_index > end_index:
                    return []
            
        verified_toc_pages = list(range(max(0, toc_pages[start_index] - start_count), toc_pages[end_index] + end_count + 1))
        utils.print_coloured(f"Verified ToC pages: {verified_toc_pages}", "green")
        return verified_toc_pages
    
    async def generate_md_string(self) -> Tuple[str, str]:
        """
        Generate Markdown strings for toc and content.
        """
        self.toc_pages = await self.find_toc_pages()
        last_toc_page = self.toc_pages[-1] + 1
        content_pages = list(range(last_toc_page, self.document.page_count))
        toc_md_string = self.to_markdown(self.document, self.toc_pages)
        content_md_string = self.to_markdown(self.document, content_pages)
        # with open("zztoc_md_string.md", "r") as f:
        #     toc_md_string = f.read()
        # with open("zzcontent_md_string.md", "r") as f:
        #     content_md_string = f.read()
        return toc_md_string, content_md_string
    
    async def map_toc_to_hierarchy(self, toc_lines: List[str], toc_hierarchy_schema: Dict[str, str]) -> Dict[str, str]:
        """
        Map the ToC sections to the hierarchy schema without llm
            - done to fix llm issue in generate_toc_hierarchy_schema
            where it will sometimes give {'Chapter': '#',...} instead of {'Chapter': '##',...}
        """
        hierarchy_map = {}
        updated_toc_hierarchy_schema = toc_hierarchy_schema.copy()
        for line in toc_lines:
            if line.strip().startswith('#'):
                level = '#' * line.count('#')
                heading_text = line.strip('#').strip()
                key = heading_text.split('—')[0].split(maxsplit=1)[0]

                if key not in hierarchy_map or len(hierarchy_map[key]) > len(level):
                    hierarchy_map[key] = level

        for key, schema_level in toc_hierarchy_schema.items():
            if key in hierarchy_map:
                updated_toc_hierarchy_schema[key] = hierarchy_map[key]
                    
        return updated_toc_hierarchy_schema

    async def generate_toc_hierarchy_schema(self) -> Dict[str, str]:
        """
        Generate a hierarchy schema for the ToC hierarchy, eg
        {
            'Chapter': '#',
            'Part': '##',
            'Division': '###',
            'Subdivision': '####'
        }
        """
        async def split_lines(lines: List[str], num_parts: int) -> List[List[str]]:
            length = len(lines)
            part_size = length // num_parts
            parts = []
            for i in range(num_parts):
                start = i * part_size
                end = (i + 1) * part_size if i < num_parts - 1 else length
                parts.append(lines[start:end])
            return parts
        
        async def create_hierarchy_schema_subset(schema: str):
            result = {}
            levels = {}
            for key, value in schema.items():
                if value not in levels:
                    levels[value] = 1
                    result[key] = value
                elif levels[value] < 2:
                    levels[value] += 1
                    result[key] = value
            return result
        
        async def process_function(toc_md_section_joined_lines: str):
            if self.no_md_flag:
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_NOMD.format(TOC_HIERARCHY_SCHEMA_TEMPLATE=prompts.TOC_HIERARCHY_SCHEMA_TEMPLATE, toc_md_string=toc_md_section_joined_lines)
            else:
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT.format(TOC_HIERARCHY_SCHEMA_TEMPLATE=prompts.TOC_HIERARCHY_SCHEMA_TEMPLATE, toc_md_string=toc_md_section_joined_lines)
            messages = [
                {"role": "system", "content": prompts.TOC_HIERARCHY_SYS_PROMPT},
                {"role": "user", "content": USER_PROMPT}
            ]
            while True:
                response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
                try:
                    if not response.choices or not response.choices[0].message:
                        print("Unexpected response structure:", response)
                        raise Exception("Unexpected response structure")
                    
                    message_content = response.choices[0].message.content
                    toc_hierarchy_schema = json.loads(message_content)
                    print(f"Schema: {json.dumps(toc_hierarchy_schema, indent=4)}")
                    if not self.no_md_flag:
                        updated_toc_hierarchy_schema = await self.map_toc_to_hierarchy(toc_md_section_lines, toc_hierarchy_schema)
                        if updated_toc_hierarchy_schema == toc_hierarchy_schema:
                            print("No changes to ToC Hierarchy Schema")
                        else:
                            print(updated_toc_hierarchy_schema)
                        return updated_toc_hierarchy_schema
                    else:
                        return toc_hierarchy_schema
                except json.JSONDecodeError:
                    print("Error decoding JSON for ToC Hierarchy Schema")
                    raise

        async def process_page(page_num: int, prior_schema: str = None):
            nonlocal unique_schema_str
            nonlocal unique_schema
            if not prior_schema:
                toc_md_toc_section_str = self.to_markdown(self.document, [page_num, page_num + 1])
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_V1SION.format(TOC_HIERARCHY_SCHEMA_TEMPLATE=prompts.TOC_HIERARCHY_SCHEMA_TEMPLATE, toc_md_string=toc_md_toc_section_str)
            else:
                toc_md_toc_section_str = self.to_markdown(self.document, [page_num])
                USER_PROMPT = prompts.TOC_HIERARCHY_USER_PROMPT_VISION.format(unique_schema_str=unique_schema_str, page_num=page_num, TOC_HIERARCHY_SCHEMA_TEMPLATE=unique_schema, toc_md_string=toc_md_toc_section_str)
            page = self.document[page_num]
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{self.encode_page_as_base64(page)}",
                            },
                        }
                    ]
                }
            ]
            if not prior_schema:
                next_page = self.document[page_num + 1]
                messages[0]["content"].append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{self.encode_page_as_base64(next_page)}",
                        },
                    }
                )
            while True:
                response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
                try:
                    message_content = response.choices[0].message.content
                    toc_hierarchy_schema = json.loads(message_content)
                    if not prior_schema:
                        ordered_items = sorted(toc_hierarchy_schema.items(), key=lambda x: x[1].count('#'))
                        ordered_dict = dict(ordered_items)
                        utils.print_coloured(f"Schema {page_num}: {json.dumps(ordered_dict, indent=2)}", "magenta")
                    return toc_hierarchy_schema
                except json.JSONDecodeError as e:
                    print(f"JSONDecodeError: {e}")
                    print(f"Message content: {message_content}")
                    print("Retrying...")
                    continue
                except Exception as e:
                    print(f"Error: {e}")
                    print("Retrying...")
                    continue
        
        # TODO: must be a better way to determine this
        toc_md_lines = self.toc_md_string.split("\n")
        toc_md_section_lines = [line for line in toc_md_lines if line.startswith('#')]
        utils.print_coloured(f"Number of ToC lines: {len(toc_md_section_lines)} out of {len(toc_md_lines)} with a ratio of {len(toc_md_section_lines) / len(toc_md_lines)}", "yellow")
        if len(toc_md_section_lines) / len(toc_md_lines) > 0.05:
            toc_md_sections = ['\n'.join(section) for section in await split_lines(toc_md_section_lines, 5)]
        else:
            self.no_md_flag = True
            utils.print_coloured("No ToC Flag Set", "yellow")
            # TODO: make toc_md_toc_section_str global
            toc_md_toc_section_str = self.to_markdown(self.document, [self.toc_pages[0], self.toc_pages[0] + 1])
            prior_schema = await process_page(self.toc_pages[0])
            unique_schema = await create_hierarchy_schema_subset(prior_schema)
            toc_md_toc_section_lines = toc_md_toc_section_str.split("\n")
            toc_md_toc_section_lines = [line for line in toc_md_toc_section_lines if line.strip()] 
            unique_schema_str = ""
            utils.print_coloured(f"Unique Schema: {json.dumps(unique_schema, indent=4)}", "cyan")
            for key, value in unique_schema.items():
                match = process.extractOne(key, [line for line in toc_md_toc_section_lines])[0]
                unique_schema_str += f"{match} -> {key}: {value}\n"
            utils.print_coloured(unique_schema_str, "magenta")

        if not self.no_md_flag:
            combined_schema = {}
            schemas = await asyncio.gather(*[self.rate_limited_process(process_function, section) for section in toc_md_sections])
        else:
            combined_schema = {re.sub(r'\s*\d+$', '', k.capitalize()): v for k, v in prior_schema.items()}
            schemas = await asyncio.gather(*[self.rate_limited_process(process_page, page_num, prior_schema=prior_schema) for page_num in self.toc_pages[2:]])
        
        # combine unique values from all schemas
        # split this up as llm was missing some values in long tocs
        #combined_schema = {}
        for schema in schemas:
            for key, value in schema.items():
                capitalised_key = re.sub(r'\s*\d+$', '', key.capitalize())
                if capitalised_key not in combined_schema: 
                    combined_schema[capitalised_key] = value

        utils.print_coloured(f"{json.dumps(combined_schema, indent=4)}", "green")

        return combined_schema

    
    async def filter_schema(self, toc_hierarchy_schema: Dict[str, str], content: str, num_sections: int = 5) -> Dict[str, str]:
        """
        Filter the schema to reduce size and complexity.
        """
        lines = self.toc_md_string.split('\n')
        grouped_schema = defaultdict(list)
        for key, value in toc_hierarchy_schema.items():
            grouped_schema[value].append(key)

        def find_most_common_heading(headings: List[str], lines: List[str]):
            counts = Counter()
            for line in lines:
                for heading in headings:
                    if heading in line:
                        counts[heading] += 1
            most_common_heading = counts.most_common(1)[0][0] if counts else None
            return most_common_heading
        
        most_common_headings = {}
        for level, headings in grouped_schema.items():
            if len(headings) > 1:
                most_common_heading = find_most_common_heading(headings, lines)
                most_common_headings[level] = most_common_heading
            else:
                most_common_headings[level] = headings[0]

        sorted_headings = sorted(most_common_headings.items(), key=lambda x: len(x[0]))
        result = {heading: level for level, heading in sorted_headings[:num_sections]}
        # dynamically adjust the schema based on whats present in the content
        for heading, level in toc_hierarchy_schema.items():
            formatted_heading = f"{level} {heading}" if not self.no_md_flag else heading
            if formatted_heading in content and heading not in result:
                result[heading] = level
        return result
    
    async def generate_toc_schema(self, levels: Dict[str, str] = None, content: str = None, depth: int = 0, max_depth: int = None) -> List[Dict[str, Any]]:
        """
        Generate a custom schema for the ToC based on the hierarchy schema.
        """
        if levels is None:
            top_level = min(self.toc_hierarchy_schema.values(), key=lambda x: x.count('#'))
            top_level_count = top_level.count('#')
            if top_level_count > 1:
                adjust_count = top_level_count - 1
                levels_unfiltered = {k: v[adjust_count:] for k, v in self.toc_hierarchy_schema.items()}
                self.adjusted_toc_hierarchy_schema = levels_unfiltered
                levels = await self.filter_schema(levels_unfiltered, content, 2) # added 2 uk companies act
                #print(f"Adjusted ToC Hierarchy Schema: {json.dumps(levels, indent=4)}")
            else:    
                levels = await self.filter_schema(self.toc_hierarchy_schema, content, 2) # added 2 uk companies act
                #print(f"UNadjusted ToC Hierarchy Schema: {json.dumps(levels, indent=4)}")

        if max_depth is None:
            max_depth = max(marker.count('#') for marker in levels.values())

        if depth >= max_depth:
            return [], levels

        current_depth_levels = [name for name, marker in levels.items() if marker.count('#') == depth + 1]
        children, _ = await self.generate_toc_schema(levels, content, depth + 1, max_depth)

        toc_schema = [
            {
                "section": f"string (type of the section, e.g., {level_name})",
                "number": "string (numeric or textual identifier of the section or empty string if not present)",
                "title": "string (title of the section or empty string if not present)",
                "children": children if children else [
                    {
                        "number": "string (numeric or textual identifier of the section)",
                        "title": "string (title of the section)"
                    },
                    {
                        "number": "string (numeric or textual identifier of the section)",
                        "title": "string (title of the section)"
                    }
                ]
            } for level_name in current_depth_levels
        ]
        return toc_schema, levels

    async def process_heading(self, heading: str) -> Dict[str, str]:
        messages = [
                {"role": "system", "content": prompts.TOC_HIERARCHY_SYS_PROMPT},
                {"role": "user", "content": prompts.TOC_SECTION_USER_PROMPT.format(TOC_SECTION_TEMPLATE=prompts.TOC_SECTION_TEMPLATE, toc_line=heading)}
            ]
        response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
        try:
            if not response.choices or not response.choices[0].message:
                print("Unexpected response structure:", response)
                raise Exception("Unexpected response structure")
            
            message_content = response.choices[0].message.content
            formatted_line = json.loads(message_content)
            print(formatted_line)
            current_part = {
                "section": formatted_line['section'],
                "number": formatted_line['number'],
                "title": formatted_line['title']
            }
            return current_part
        except Exception as e:
            print(f"process_heading error loading json: {e}")

    async def split_toc_parts_into_parts(self, lines: List[str], level_types: List[str]) -> Dict[str, Union[str, Dict]]:
        """
        Split the ToC parts into sub-parts based on the sub-part type, 
        processing headings concurrently while maintaining the original structure.
        """
        parts = {}
        stack = []
        i = 0
        heading_futures = []

        async def process_heading_queue():
            return await asyncio.gather(*[future for future, _ in heading_futures])

        while i < len(lines):
            line = lines[i]
            level = None
            for j, level_type in enumerate(level_types):
                if line.startswith(level_type):
                    level = j
                    break
            if level is not None:
                heading = line.strip()
                j = 1
                while i + j < len(lines) and lines[i + j].startswith(level_types[level].split(" ")[0] + ' '):
                    next_line = lines[i + j].strip().lstrip('#').strip()
                    heading += ' ' + next_line
                    j += 1
                # strip last number from heading (pagenumber)
                heading = re.sub(r'\s\d+$', '', heading)
                placeholder = str(uuid.uuid4())  

                while stack and stack[-1][0] >= level:
                    stack.pop()
                if stack:
                    parent = stack[-1][1]
                    if "children" not in parent:
                        parent["children"] = {}
                    parent["children"][placeholder] = {}
                    stack.append((level, parent["children"][placeholder]))
                else:
                    parts[placeholder] = {}
                    stack.append((level, parts[placeholder]))

                heading_futures.append((self.rate_limited_process(self.process_heading, heading), placeholder)) 
                i += j
            else:
                if stack:
                    if line.strip():
                        if "content" not in stack[-1][1]:
                            stack[-1][1]["content"] = ""
                        stack[-1][1]["content"] += re.sub(r'\s\d+$', '', line.strip()) + '\n'
                i += 1

        processed_headings = await process_heading_queue() 
        for processed_heading, original_heading in zip(processed_headings, [heading for _, heading in heading_futures]):
            def replace_heading(data):
                if isinstance(data, dict):
                    for key in list(data.keys()): 
                        if key == original_heading:
                            data[json.dumps(processed_heading)] = data.pop(original_heading)
                        else:
                            replace_heading(data[key])
            replace_heading(parts)
        return parts
    
    async def split_no_md_toc_parts_into_parts(self, lines: List[str], level_types: List[str]) -> Dict[str, Union[str, Dict]]:
        parts = {}
        stack = []
        i = 0
        heading_futures = []

        async def process_heading_queue():
            return await asyncio.gather(*[future for future, _ in heading_futures])
        
        while i < len(lines):
            line = lines[i].strip()
            level = None
            for level_type, level_num in level_types:
                # if level_type in line:
                if line.lower().startswith(f"**{level_type.lower()}"):
                    level = level_num
                    break
            if level is not None:
                heading = line.strip()
                placeholder = str(uuid.uuid4())
                heading_futures.append((self.rate_limited_process(self.process_heading, heading), placeholder))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                if stack:
                    parent = stack[-1][1]
                    if "children" not in parent:
                        parent["children"] = {}
                    parent["children"][placeholder] = {}
                    stack.append((level, parent["children"][placeholder]))
                else:
                    parts[placeholder] = {}
                    stack.append((level, parts[placeholder]))
                i += 1
            else:
                if stack:
                    if line.strip():
                        if "content" not in stack[-1][1]:
                            stack[-1][1]["content"] = ""
                        stack[-1][1]["content"] += line.strip() + '\n'
                i += 1

        processed_headings = await process_heading_queue()
        for processed_heading, original_heading in zip(processed_headings, [heading for _, heading in heading_futures]):
            def replace_heading(data):
                if isinstance(data, dict):
                    for key in list(data.keys()): 
                        if key == original_heading:
                            data[json.dumps(processed_heading)] = data.pop(original_heading)
                        else:
                            replace_heading(data[key])
            replace_heading(parts)
        return parts
    
    async def split_toc_into_parts(self) -> Dict[str, Union[str, Dict[str, str]]]:
        """
        Split the ToC into parts based on the hierarchy schema and token count
        """
        lines_dirty = self.toc_md_string.split('\n')
        lines = [line for line in lines_dirty if line.strip()]
        grouped_schema = defaultdict(list)
        for key, value in self.toc_hierarchy_schema.items():
            grouped_schema[value].append(key)

        def find_most_common_heading(headings: List[str], lines: List[str]):
            counts = Counter()
            for line in lines:
                for heading in headings:
                    if heading in line:
                        counts[heading] += 1
            most_common_heading = counts.most_common(1)[0][0] if counts else None
            return most_common_heading
        
        most_common_headings = {}
        for level, headings in grouped_schema.items():
            if len(headings) > 1:
                most_common_heading = find_most_common_heading(headings, lines)
                most_common_headings[level] = most_common_heading
            else:
                most_common_headings[level] = headings[0]
        
        if self.no_md_flag:
            sorted_headings = sorted(self.toc_hierarchy_schema.items(), key=lambda x: x[1].count('#'))
            level_types = [(heading, level.count('#')) for heading, level in sorted_headings[:3]]
            print(level_types)
            #level_types = [('SCHEDULES', 1), ('APPENDICES', 1), ('PART', 1)] #RAMSAY NURSES ALWAYS WRONG
            return await self.split_no_md_toc_parts_into_parts(lines, level_types)
        else:
            sorted_headings = sorted(most_common_headings.items(), key=lambda x: len(x[0]))
            level_types = [f"{level[0]} {level[1]}" for level in sorted_headings][:3] # only take the top 3 levels
            return await self.split_toc_parts_into_parts(lines, level_types)
    
    async def generate_formatted_toc(self, level_title: JSONstr, sublevel_title: Union[JSONstr, None], subsublevel_title: Union[JSONstr, None], content: str) -> Tuple[JSONstr, JSONstr, JSONstr, Dict[str, Any]]:

        async def process_function():
            nonlocal sublevel_title
            nonlocal subsublevel_title
            custom_schema, custom_levels = await self.generate_toc_schema(content=content)
            TOC_SCHEMA = {"contents": [json.dumps(custom_schema, indent=4)]}
            
            if self.no_md_flag:
                section_types = ", ".join(custom_levels.keys())
                level_title_dict = json.loads(level_title)
                level_title_str = f"{level_title_dict['section']} {level_title_dict.get('number', '')} {level_title_dict['title']}"
                sublevel_title_str = ""
                subsublevel_title_str = ""
                messages = [
                    {"role": "system", "content": prompts.TOC_SCHEMA_SYS_PROMPT_PLUS},
                    {"role": "user", "content": prompts.TOC_SCHEMA_USER_PROMPT.format(level_title=level_title_str, section_types=section_types, TOC_SCHEMA=TOC_SCHEMA, content=content)}
                ]
                messages_str = json.dumps(messages, indent=4)
                utils.print_coloured(f"{level_title_str} ({self.count_tokens(messages_str)} tokens)", "red")
                sublevel_title = "Complete"
                subsublevel_title = "Complete"
            else:
                section_types = ", ".join(custom_levels.keys())
                level_title_dict = json.loads(level_title)
                level_title_str = f"{level_title_dict['section']} {level_title_dict['number']} {level_title_dict['title']}"
                if sublevel_title:
                    sublevel_title_dict = json.loads(sublevel_title)
                    sublevel_title_str = f"{sublevel_title_dict['section']} {sublevel_title_dict['number']} {sublevel_title_dict['title']}"
                else:
                    sublevel_title_str = ""
                    sublevel_title = "Complete"
                if subsublevel_title:
                    subsublevel_title_dict = json.loads(subsublevel_title)
                    subsublevel_title_str = f"{subsublevel_title_dict['section']} {subsublevel_title_dict['number']} {subsublevel_title_dict['title']}"
                else:
                    subsublevel_title_str = ""
                    subsublevel_title = "Complete"
                messages = [
                    {"role": "system", "content": prompts.TOC_SCHEMA_SYS_PROMPT_PLUS},
                    {"role": "user", "content": prompts.TOC_SCHEMA_USER_PROMPT_PLUS.format(level_title=level_title_str, sublevel_title=sublevel_title_str, subsublevel_title=subsublevel_title_str, section_types=section_types, TOC_SCHEMA=TOC_SCHEMA, content=content)}
                ]
            response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
            if not response.choices or not response.choices[0].message:
                print("Unexpected response structure:", response)
                raise Exception("Unexpected response structure")
            if response.choices[0].finish_reason == "length":
                utils.print_coloured(f"TOO LONG: {level_title_str} / {sublevel_title_str} / {subsublevel_title_str}", "red")
                inital_message_content = response.choices[0].message.content
                split_content = inital_message_content.rsplit('},', 1)
                if len(split_content) == 2:
                    inital_message_content, remaining_content = split_content
                    remaining_content = '},' + remaining_content.strip()
                    utils.print_coloured(remaining_content, "yellow")
                else:
                    remaining_content = ''
                additional_messages = [
                    {"role": "assistant", "content": inital_message_content},
                    {"role": "user", "content": "Please continue from EXACTLY where you left off so that the two responses can be concatenated and form a complete JSON object. Make sure to include the closing brackets, quotation marks and commas. Do NOT add any additional text, such as '```json' or '```'."},
                    {"role": "assistant", "content": remaining_content}]
                combined_messages = messages + additional_messages
                retries = 0
                max_retries = 5
                while retries < max_retries:
                    response2 = await llm.openai_client_chat_completion_request(combined_messages, model="gpt-4o", response_format="text")
                    try:
                        message_content2 = response2.choices[0].message.content
                        utils.print_coloured(message_content2, "yellow")
                        # if message_content2.startswith("},") == False:
                        #     message_content2 = "}," + message_content2
                        if message_content2.startswith(remaining_content) == False:
                            message_content2 = remaining_content + message_content2
                        total_message_content = inital_message_content + message_content2
                        toc_schema = json.loads(total_message_content)
                        utils.print_coloured(f"{level_title_str} / {sublevel_title_str} / {subsublevel_title_str}", "green")
                        return (level_title, sublevel_title, subsublevel_title, toc_schema)
                    except json.JSONDecodeError:
                        retries += 1
                        utils.print_coloured(f"Error decoding TOO LONG JSON ... / {subsublevel_title_str}, attempt {retries}", "red")
                        if retries >= max_retries:
                            raise Exception("Max retries reached, unable to complete JSON")
            try:
                message_content = response.choices[0].message.content
                toc_schema = json.loads(message_content)
                # try:
                #     TableOfContentsDict(**toc_schema)
                # except ValidationError as e:
                #     utils.print_coloured(f"Validation error for {level_title_str} / {sublevel_title_str} / {subsublevel_title_str}: {e}", "red")
                    #raise
                utils.print_coloured(f"{level_title_str} / {sublevel_title_str} / {subsublevel_title_str}", "green")
                return (level_title, sublevel_title, subsublevel_title, toc_schema)
            except json.JSONDecodeError:
                print(f"Error decoding JSON for {level_title} - {sublevel_title}")
                raise

        return await self.rate_limited_process(process_function)
    
    async def extract_toc(self) -> TableOfContentsDict:
        """
        Extract and format the ToC.
        """
        levels = await self.split_toc_into_parts()
        # with open("levels.json", "r") as f:
        #     levels = json.load(f)
        tasks = []
        all_level_schemas = {"contents": []}
        with open("levels.json", "w") as f:
            json.dump(levels, f, indent=4)

        async def process_level(level_title, level_content, sublevel_title=None, subsublevel_title=None):
            if "content" in level_content:
                # if there is content, generate the formatted ToC request
                task = asyncio.create_task(self.generate_formatted_toc(level_title, sublevel_title, subsublevel_title, level_content["content"]))
                tasks.append(task)

            if "children" in level_content:
                # process each child level recursively
                for child_title, child_content in level_content["children"].items():
                    if "children" in child_content:
                        # process further children, process them as subsublevels
                        for subchild_title, subchild_content in child_content["children"].items():
                            await process_level(level_title, subchild_content, child_title, subchild_title)
                    else:
                        await process_level(level_title, child_content, child_title)
        
        async def process_level_no_md(level_title, level_content, sublevel_title=None, subsublevel_title=None):
            if "content" in level_content:
                if level_content["content"].count('\n') == 1:
                    level_title_dict = json.loads(level_title)
                    if not level_title_dict["title"]:
                        level_title_dict["title"] = level_content["content"]
                        level_title = json.dumps(level_title_dict)
                else:
                    # if there is content, generate the formatted ToC request
                    task = asyncio.create_task(self.generate_formatted_toc(level_title, sublevel_title, subsublevel_title, level_content["content"]))
                    tasks.append(task)

            if "children" in level_content:
                # process each child level recursively
                for child_title, child_content in level_content["children"].items():
                    if "children" in child_content:
                        # process further children, process them as subsublevels
                        for subchild_title, subchild_content in child_content["children"].items():
                            await process_level_no_md(level_title, subchild_content, child_title, subchild_title)
                    else:
                        await process_level_no_md(level_title, child_content, child_title)

        if not self.no_md_flag:
            for level_title, level_content in levels.items():
                await process_level(level_title, level_content)
        else:
            for level_title, level_content in levels.items():
                await process_level_no_md(level_title, level_content)

        try:
            results = await asyncio.gather(*tasks)
            for level_title, sublevel_title, subsublevel_title, result in results:
                if result and result.get('contents'):
                    all_level_schemas["contents"].append({
                        "level": level_title,
                        "sublevel": sublevel_title,
                        "subsublevel": subsublevel_title,
                        "toc": result['contents']
                    })
        except Exception as e:
            print(f"Error extracting ToC: {e}")

        return all_level_schemas
    
    async def find_existing_section(self, toc: List[TableOfContents], section: str, number: str) -> Optional[TableOfContents]:
        """find an existing section by section and number."""
        for item in toc:
            if item.section == section and item.number == number:
                return item
        return None
    
    async def nest_toc(self, content: Contents) -> TableOfContents:
        """builds a nested table of contents based on content levels"""
        def parse_level(level_json: JSONstr):
            level_dict = json.loads(level_json)
            return level_dict['section'], level_dict['number'], level_dict['title']
        
        def find_nested_toc(tocs: List[Union[TableOfContents, TableOfContentsChild]], section: str, number: str) -> Optional[TableOfContents]:
            """recursively search for a TableOfContents by section and number in nested children"""
            for toc in tocs:
                if isinstance(toc, TableOfContents):
                    if toc.section == section and toc.number == number:
                        return toc
                    found = find_nested_toc(toc.children or [], section, number)
                    if found:
                        return found
            return None
        
        level_section, level_number, level_title = parse_level(content.level)
        result_toc = TableOfContents(section=level_section, number=level_number, title=level_title, children=[])
        if content.sublevel == "Complete":
            level_toc = find_nested_toc(content.toc, level_section, level_number)
            if level_toc:
                result_toc.children = level_toc.children
            else:
                result_toc.children = content.toc 
        else:
            sublevel_section, sublevel_number, sublevel_title = parse_level(content.sublevel)
            sublevel_toc = TableOfContents(section=sublevel_section, number=sublevel_number, title=sublevel_title, children=[])
            result_toc.children = [sublevel_toc]

            if content.subsublevel == "Complete":
                found_sublevel_toc = find_nested_toc(content.toc, sublevel_section, sublevel_number)
                if found_sublevel_toc:
                    utils.print_coloured(f"sublevel_toc: {found_sublevel_toc}", "cyan")
                    sublevel_toc.children = [found_sublevel_toc]
                else:
                    sublevel_toc.children = content.toc
            else:
                subsublevel_section, subsublevel_number, subsublevel_title = parse_level(content.subsublevel)
                subsublevel_toc = TableOfContents(section=subsublevel_section, number=subsublevel_number, title=subsublevel_title, children=[])
                sublevel_toc.children = [subsublevel_toc]

                found_subsublevel_toc = find_nested_toc(content.toc, subsublevel_section, subsublevel_number)
                if found_subsublevel_toc:
                    utils.print_coloured(f"subsublevel_toc: {found_subsublevel_toc}", "green")
                    subsublevel_toc.children = [found_subsublevel_toc]
                else:
                    subsublevel_toc.children = content.toc

        return result_toc
        
    async def merge_toc(self, master_toc: List[TableOfContents], toc: List[TableOfContents], ) -> List[TableOfContents]:
        """
        merge ToC sections
        """
        sorted_schema = sorted(self.toc_hierarchy_schema.items(), key=lambda item: len(item[1]))
        top_level_type = sorted_schema[0][0]
        existing_level = await self.find_existing_section(master_toc, top_level_type, toc.number)
        if existing_level:
            existing_level.children = merge_children(existing_level.children, toc.children or [])
        else:
            master_toc.append(toc)

    async def build_master_toc(self, data: TableOfContentsDict) -> List[TableOfContents]:
        """
        build the master ToC from the split ToC parts
        """
        master_toc: List[TableOfContents] = []
        for content in data.contents:
            toc = await self.nest_toc(content)
            await self.merge_toc(master_toc, toc)
        self.master_toc = [toc.model_dump() for toc in master_toc]
        self.save_toc_to_file(master_toc, "master_toc.json")
        return master_toc
    
    def save_toc_to_file(self, toc: List[TableOfContents], file_name: str):
        """temp for testing"""
        with open(file_name, "w") as file:
            json.dump(toc, file, indent=2, default=lambda x: x.dict())
    
    async def generate_master_toc_content(self) -> Dict[str, Dict[Any]]:
        """
        add the document content to the master ToC.
        """
        # content_md_lines = self.content_md_string.split("\n")
        # content_md_section_lines = [(line, idx) for idx, line in enumerate(content_md_lines) if line.startswith('#')]
        def format_md_lines():
            content_md_lines = self.content_md_string.split("\n")
            content_md_section_lines = []
            processed_lines = []
            for i in range(len(content_md_lines)):
                line = content_md_lines[i]
                if line.startswith('#') and i not in processed_lines:
                    current_part = line.strip()
                    j = 1
                    while i + j < len(content_md_lines) and content_md_lines[i + j].startswith('#'):
                        next_line = content_md_lines[i + j].strip().lstrip('#').strip()
                        current_part += ' ' + next_line
                        processed_lines.append(i + j)
                        j += 1
                    content_md_section_lines.append((current_part, i))
            return content_md_lines, content_md_section_lines
        
        content_md_lines, content_md_section_lines = format_md_lines()
        if self.no_md_flag:
            content_md_section_lines = [(line, idx) for idx, line in enumerate(content_md_lines)]
        with open("zzcontent_md_section_lines.md", "w") as f:
            f.write("\n".join([f"{line} [{idx}]" for line, idx in content_md_section_lines]))

        md_levels = self.adjusted_toc_hierarchy_schema if self.adjusted_toc_hierarchy_schema else self.toc_hierarchy_schema

        def format_section_name(section: str, number: str, title: str) -> str:
            section_match = process.extractOne(section, md_levels.keys(), score_cutoff=98) if section else None
            md_level = md_levels.get(section_match[0], max(md_levels.values(), key=len) + "#") if section_match else max(md_levels.values(), key=len) + "#"

            formatted_parts = []
            if section and not section in title:
                formatted_parts.append(section)
            if number and not number in title:
                formatted_parts.append(number)
            if title:
                formatted_parts.append(title)

            return f'{md_level} {" ".join(formatted_parts)}'
            
        def traverse_and_update_toc(master_toc: List[Dict[str, Any]]):
            levels_dict = {"contents": []}

            def convert_to_model(data: Dict[str, Any]) -> Union[TableOfContents, TableOfContentsChild]:
                if 'children' in data:
                    data['children'] = [convert_to_model(child) for child in data['children']]
                    return TableOfContents(**data)
                else:
                    return TableOfContentsChild(**data)

            def flatten_toc(toc_models: List[Union[TableOfContents, TableOfContentsChild]]) -> List[Union[TableOfContents, TableOfContentsChild]]:
                flattened = []
                for model in toc_models:
                    if isinstance(model, TableOfContents):
                        flattened.append(model)
                        if model.children:
                            flattened.extend(flatten_toc(model.children))
                    elif isinstance(model, TableOfContentsChild):
                        flattened.append(model)
                return flattened
            
            remaining_content_md_section_lines = content_md_section_lines.copy()
            #def get_section_content(next_formatted_section_name: str, formatted_section_name: str = None) -> Tuple[str, int]:
            def get_section_content(next_section: Tuple[str, str, str], section: Tuple[str, str, str] = None) -> Tuple[str, int]:
                nonlocal remaining_content_md_section_lines
                if section:
                    formatted_section_name = format_section_name(*section)
                    start_matches = process.extractBests(formatted_section_name, [line for line, _ in remaining_content_md_section_lines], score_cutoff=80, limit=10)
                    if start_matches:
                        start_highest_score = max(start_matches, key=lambda x: x[1])[1]
                        start_highest_score_matches = [match for match in start_matches if match[1] == start_highest_score]
                        start_matched_line = min(start_highest_score_matches, key=lambda x: next(idx for line, idx in remaining_content_md_section_lines if line == x[0]))[0]
                        start_line_idx = next(idx for line, idx in remaining_content_md_section_lines if line == start_matched_line)
                    else:
                        print(f"Could not match start: {formatted_section_name}")
                        start_line_idx = remaining_content_md_section_lines[0][1]
                else:
                    start_line_idx = remaining_content_md_section_lines[0][1]

                if next_section:
                    next_formatted_section_name = format_section_name(*next_section)
                    next_number = next_section[1] if next_section[1] else ""
                    if next_number:
                        filtered_remaining_content_md_section_lines = [(line, idx) for line, idx in remaining_content_md_section_lines if next_number in line]
                        matches = process.extractBests(next_formatted_section_name, [line for line, _ in filtered_remaining_content_md_section_lines], score_cutoff=80, limit=10)
                    else:
                        matches = process.extractBests(next_formatted_section_name, [line for line, _ in remaining_content_md_section_lines], score_cutoff=80, limit=10)
                    if matches:
                        highest_score = max(matches, key=lambda x: x[1])[1]
                        highest_score_matches = [match for match in matches if match[1] == highest_score]
                        matched_line = min(highest_score_matches, key=lambda x: next(idx for line, idx in remaining_content_md_section_lines if line == x[0]))[0]
                        line_idx = next(idx for line, idx in remaining_content_md_section_lines if line == matched_line)
                        print(f"Match: {next_formatted_section_name}: {matched_line} [{line_idx}]")
                    else:
                        for line, idx in remaining_content_md_section_lines:
                            print(f"Line: {line} [{idx}]")
                        raise ValueError(f"Could not match end: {next_formatted_section_name}")
                else:
                    line_idx = len(content_md_lines)

                section_content = "\n".join(content_md_lines[start_line_idx:line_idx-1])
                num_tokens = self.count_tokens(section_content)
                remaining_content_md_section_lines = [item for item in remaining_content_md_section_lines if item[1] >= line_idx]
                return section_content, num_tokens
                    

            def traverse_sections(sections: List[Union[TableOfContents, TableOfContentsChild]], parent_dict: Dict[str, Any], flattened_toc: List[Union[TableOfContents, TableOfContentsChild]]):
                for section in sections:
                    if isinstance(section, TableOfContents):
                        formatted_section_name = format_section_name(section.section, section.number, section.title)
                        section_dict = {
                            "section": section.section,
                            "number": section.number,
                            "title": section.title,
                            "content": "",
                            "tokens": 0,
                            "children": []
                        }
                        parent_dict["children"].append(section_dict)

                        current_index = flattened_toc.index(section)
                        if current_index + 1 < len(flattened_toc):
                            next_item = flattened_toc[current_index + 1]
                            #next_formatted_section_name = format_section_name(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else format_section_name("", next_item.number, next_item.title)

                            # section_content, section_tokens = get_section_content(next_formatted_section_name=next_formatted_section_name)
                            section_content, section_tokens = get_section_content(next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else ("", next_item.number, next_item.title))
                            if len(section_content) > len(formatted_section_name)*1.3:
                                section_dict["content"] = section_content
                                section_dict["tokens"] = section_tokens


                        if section.children:
                            traverse_sections(section.children, section_dict, flattened_toc)
                    
                    elif isinstance(section, TableOfContentsChild):
                        #formatted_section_name = format_section_name("", section.number, section.title)
                        child_dict = {
                            "number": section.number,
                            "title": section.title,
                            "content": "",
                            "tokens": 0
                        }
                        parent_dict["children"].append(child_dict)

                        current_index = flattened_toc.index(section)
                        if current_index + 1 < len(flattened_toc):
                            next_item = flattened_toc[current_index + 1]
                            # next_formatted_section_name = format_section_name(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else format_section_name("", next_item.number, next_item.title)

                            # section_content, section_tokens = get_section_content(next_formatted_section_name=next_formatted_section_name)
                            section_content, section_tokens = get_section_content(next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else ("", next_item.number, next_item.title))
                            child_dict["content"] = section_content
                            child_dict["tokens"] = section_tokens
                        else:
                            section_content, section_tokens = get_section_content(next_section="")
                            child_dict["content"] = section_content
                            child_dict["tokens"] = section_tokens
            
            toc_models = [convert_to_model(item) for item in master_toc]
            flattened_toc = flatten_toc(toc_models)
            
            for item in toc_models:
                formatted_section_name = format_section_name(item.section, item.number, item.title)
                section_dict = {
                    "section": item.section,
                    "number": item.number,
                    "title": item.title,
                    "content": "",
                    "tokens": 0,
                    "children": []
                }
                levels_dict["contents"].append(section_dict)
                
                current_index = flattened_toc.index(item)
                if current_index + 1 < len(flattened_toc):
                    next_item = flattened_toc[current_index + 1]
                    # if isinstance(next_item, TableOfContents):
                    #     next_formatted_section_name = format_section_name(next_item.section, next_item.number, next_item.title)
                    # elif isinstance(next_item, TableOfContentsChild):
                    #     next_formatted_section_name = format_section_name("", next_item.number, next_item.title)
                    
                    # section_content, section_tokens = get_section_content(formatted_section_name=formatted_section_name, next_formatted_section_name=next_formatted_section_name)
                    section_content, section_tokens = get_section_content(section=(item.section, item.number, item.title), next_section=(next_item.section, next_item.number, next_item.title) if isinstance(next_item, TableOfContents) else ("", next_item.number, next_item.title))
                    if len(section_content) > len(formatted_section_name)*1.3:
                        section_dict["content"] = section_content
                        section_dict["tokens"] = section_tokens
                
                traverse_sections(item.children, section_dict, flattened_toc)
            
            return levels_dict
        
        return traverse_and_update_toc(self.master_toc)

        
    
    async def parse(self, file: Union[UploadFile, str]) -> Dict[str, Dict[Any]]:
        """
        Main method to parse the PDF content.
        """
        await self.load_document(file)
        toc = await self.extract_toc()
        with open("toc.json", "w") as f:
            json.dump(toc, f, indent=4)
        data = TableOfContentsDict(**toc)
        await self.build_master_toc(data)
        content_dict = await self.generate_master_toc_content()
        return content_dict