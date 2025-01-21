import pdfplumber
import fitz  # PyMuPDF
import html
import os
import base64
from PIL import Image
from io import BytesIO
from typing import Dict, List, Tuple


class PDFToHTMLConverter:
    def __init__(self):

        self.html_template = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>{title}</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 40px; }}
                .page {{ margin-bottom: 20px; border-bottom: 1px solid #ccc; padding-bottom: 20px; }}
                .text-block {{ margin-bottom: 10px; }}
                table {{ border-collapse: collapse; margin: 15px 0; width: 100%; }}
                th, td {{ 
                    border: 1px solid #ddd; 
                    padding: 8px; 
                    text-align: left; 
                }}
                th {{ background-color: #f5f5f5; }}
                .service-cell {{
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }}
                .service-icon {{
                    width: 24px;
                    height: 24px;
                    object-fit: contain;
                    vertical-align: middle;
                    margin-right: 8px;
                }}
                .service-name {{
                    color: #1155cc;
                    vertical-align: middle;
                }}
            </style>
        </head>
        <body>
            {content}
        </body>
        </html>
        """

    def get_image_for_service(
        self, service_name: str, page_images: list, cell_bbox: tuple
    ) -> dict:
        """Find the icon image associated with a service name with improved positioning logic"""
        cell_x_center = (cell_bbox[0] + cell_bbox[2]) / 2
        cell_y_center = (cell_bbox[1] + cell_bbox[3]) / 2

        closest_image = None
        min_distance = float("inf")

        for image in page_images:
            img_x_center = (image["bbox"][0] + image["bbox"][2]) / 2
            img_y_center = (image["bbox"][1] + image["bbox"][3]) / 2

            # Calculate distance from cell center to image center
            distance = (
                (img_x_center - cell_x_center) ** 2
                + (img_y_center - cell_y_center) ** 2
            ) ** 0.5

            # Check if image is within or very close to cell boundaries
            is_near_cell = (
                abs(img_x_center - cell_x_center) < 50  # Increased tolerance
                and abs(img_y_center - cell_y_center) < 30  # Vertical tolerance
            )

            if is_near_cell and distance < min_distance:
                min_distance = distance
                closest_image = image

        return closest_image

    def get_image_rect(self, page, xref):
        """Get image rectangle by searching all page drawings"""
        for draw in page.get_drawings():
            if hasattr(draw, "get") and draw.get("fill_image", None) == xref:
                return draw["rect"]
        return None

    def extract_images_from_page(self, pdf_doc, page_num):
        """Extract all images from a page including their positions"""
        page = pdf_doc[page_num]
        images = []

        # Get list of image objects
        image_list = page.get_images(full=True)

        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]  # xref is always the first element
            base_image = pdf_doc.extract_image(xref)

            if base_image:
                try:
                    # Convert image data to PIL Image
                    image_data = base_image["image"]
                    image_format = base_image["ext"]
                    img = Image.open(BytesIO(image_data))

                    # Convert to base64
                    buffered = BytesIO()
                    img.save(buffered, format=image_format.upper())
                    img_base64 = base64.b64encode(buffered.getvalue()).decode()

                    # Try to get image position
                    rect = self.get_image_rect(page, xref)
                    if rect:
                        bbox = (rect[0], rect[1], rect[2], rect[3])
                    else:
                        # Fallback: Use page size for bbox
                        page_rect = page.rect
                        bbox = (0, 0, page_rect.width, page_rect.height)

                    images.append(
                        {
                            "data": img_base64,
                            "format": image_format,
                            "bbox": bbox,
                            "width": bbox[2] - bbox[0],
                            "height": bbox[3] - bbox[1],
                        }
                    )

                except Exception as e:
                    print(f"Warning: Failed to process image: {str(e)}")
                    continue

        return images

    def is_image_in_cell(self, image, cell_bbox):
        """Check if an image belongs inside a table cell"""
        img_x = (image["bbox"][0] + image["bbox"][2]) / 2
        img_y = (image["bbox"][1] + image["bbox"][3]) / 2

        return (
            cell_bbox[0] <= img_x <= cell_bbox[2]
            and cell_bbox[1] <= img_y <= cell_bbox[3]
        )

    # def extract_tables_with_images(self, page, page_images):
    #     """Extract tables and integrate all images into table cells"""
    #     tables_html = []
    #     tables = page.extract_tables()
    #     found_tables = page.find_tables()

    #     for table_index, table in enumerate(tables):
    #         if not table:
    #             continue

    #         table_html = '<table style="width:100%; border-collapse:collapse;">\n'
    #         table_bbox = found_tables[table_index].bbox

    #         for row_index, row in enumerate(table):
    #             table_html += "<tr>\n"

    #             # Calculate row boundaries
    #             row_height = (table_bbox[3] - table_bbox[1]) / len(table)
    #             row_y_top = table_bbox[1] + (row_height * row_index)
    #             row_y_bottom = row_y_top + row_height

    #             for col_index, cell in enumerate(row):
    #                 # Calculate column boundaries
    #                 col_width = (table_bbox[2] - table_bbox[0]) / len(row)
    #                 cell_x_left = table_bbox[0] + (col_width * col_index)
    #                 cell_x_right = cell_x_left + col_width
    #                 cell_bbox = (cell_x_left, row_y_top, cell_x_right, row_y_bottom)

    #                 # Handle header row differently
    #                 if row_index == 0:
    #                     table_html += f'<th style="border:1px solid #ddd; padding:8px; text-align:left;">'
    #                     if cell:
    #                         table_html += html.escape(str(cell))
    #                     table_html += "</th>\n"
    #                 else:
    #                     # Handle data cells
    #                     table_html += f'<td style="border:1px solid #ddd; padding:8px; vertical-align:middle;">'
                        
    #                     # Only look for images in data rows, not header
    #                     cell_images = []
    #                     for img in page_images[:]:
    #                         img_center_x = (img["bbox"][0] + img["bbox"][2]) / 3
    #                         if (cell_x_left - 3000 <= img_center_x <= cell_x_right + 3000):
    #                             cell_images.append(img)
    #                             page_images.remove(img)

    #                     if col_index == 0:  # First column
    #                         table_html += '<div class="service-cell">'
    #                         # Add images first
    #                         if cell_images:
    #                             for img in cell_images:
    #                                 table_html += (
    #                                     f'<img src="data:image/{img["format"]};base64,{img["data"]}" '
    #                                     'class="service-icon" alt="Service icon">'
    #                                 )
    #                         # Then add service name
    #                         if cell:
    #                             table_html += f'<span class="service-name">{html.escape(str(cell))}</span>'
    #                         table_html += '</div>'
    #                     else:  # Other columns
    #                         if cell_images:
    #                             for img in cell_images:
    #                                 table_html += (
    #                                     f'<img src="data:image/{img["format"]};base64,{img["data"]}" '
    #                                     'style="width:30px; height:30px; vertical-align:middle; margin-right:10px;" '
    #                                     f'alt="Table image">'
    #                                 )
    #                         if cell:
    #                             table_html += html.escape(str(cell))
                        
    #                     table_html += "</td>\n"

    #             table_html += "</tr>\n"

    #         # Handle any remaining images
    #         if page_images:
    #             table_html += '<tr><td colspan="3" style="border:1px solid #ddd; padding:8px;">'
    #             for img in page_images[:]:
    #                 table_html += (
    #                     f'<img src="data:image/{img["format"]};base64,{img["data"]}" '
    #                     'style="width:30px; height:30px; margin-right:10px; vertical-align:middle;" '
    #                     f'alt="Additional image">'
    #                 )
    #                 page_images.remove(img)
    #             table_html += "</td></tr>"

    #         table_html += "</table>"
    #         tables_html.append(table_html)

    #     return tables_html

    def extract_tables_with_images(self, page, page_images):
        """Extract tables and ensure each service row has its own image in the correct td tag"""
        tables_html = []
        tables = page.extract_tables()
        found_tables = page.find_tables()

        for table_index, table in enumerate(tables):
            if not table:
                continue

            table_html = '<table style="width:100%; border-collapse:collapse;">\n'
            table_bbox = found_tables[table_index].bbox

            # Process header row first
            table_html += "<tr>\n"
            for header_cell in table[0]:
                table_html += f'<th style="border:1px solid #ddd; padding:8px; text-align:left;">'
                table_html += html.escape(str(header_cell)) if header_cell else ''
                table_html += "</th>\n"
            table_html += "</tr>\n"

            # Sort images by vertical position for row matching
            sorted_images = sorted(page_images, key=lambda x: (x["bbox"][1] + x["bbox"][3]) / 2)
            
            # Process each data row
            for row_index in range(1, len(table)):
                row = table[row_index]
                row_height = (table_bbox[3] - table_bbox[1]) / len(table)
                row_y = table_bbox[1] + (row_height * row_index)
                
                # Start new row
                table_html += "<tr>\n"
                
                for col_index, cell in enumerate(row):
                    if col_index == 0:  # First column (service column)
                        table_html += f'<td style="border:1px solid #ddd; padding:8px; vertical-align:middle;">'
                        table_html += '<div class="service-cell">'
                        
                        # Try to find an image for this row
                        if sorted_images:
                            img = sorted_images.pop(0)  # Get the next available image
                            table_html += (
                                f'<img src="data:image/{img["format"]};base64,{img["data"]}" '
                                'class="service-icon" alt="Service icon">'
                            )
                        
                        # Add service name
                        if cell:
                            table_html += f'<span class="service-name">{html.escape(str(cell))}</span>'
                        
                        table_html += '</div></td>\n'
                    else:
                        # Regular cell
                        table_html += f'<td style="border:1px solid #ddd; padding:8px;">'
                        table_html += html.escape(str(cell)) if cell else ''
                        table_html += '</td>\n'
                
                table_html += "</tr>\n"

            table_html += "</table>"
            tables_html.append(table_html)

        return tables_html

    def extract_pdf_content(self, pdf_path: str) -> List[Dict]:
        """Extract text, tables with images, and standalone images from PDF file"""
        pages_content = []

        try:
            pdf_doc = fitz.open(pdf_path)

            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_images = self.extract_images_from_page(pdf_doc, page_num)
                    tables = self.extract_tables_with_images(page, page_images)

                    standalone_images = []
                    if page_images:
                        for img in page_images:
                            is_in_table = False
                            for table in page.find_tables():
                                if self.is_image_in_cell(img, table.bbox):
                                    is_in_table = True
                                    break
                            if not is_in_table:
                                standalone_images.append(img)

                    content = {
                        "text": page.extract_text(),
                        "tables": tables,
                        "images": standalone_images,
                        "page_number": page.page_number,
                    }
                    pages_content.append(content)

            pdf_doc.close()

        except Exception as e:
            raise Exception(f"Error extracting PDF content: {str(e)}")

        return pages_content

    def convert_to_html(
        self, pages_content: List[Dict], title: str = "PDF Conversion"
    ) -> str:
        """Convert extracted PDF content to HTML with proper table formatting"""
        html_content = ""

        for page in pages_content:
            page_html = f'<div class="page" id="page-{page["page_number"]}">\n'
            page_html += f'<h2>Page {page["page_number"]}</h2>\n'

            # Add tables first
            for table in page["tables"]:
                page_html += table + "\n"

            # Add only images that weren't used in tables
            for img in page.get("images", []):
                if not any(img.get("data", "") in table for table in page["tables"]):
                    page_html += (
                        f'<img src="data:image/{img["format"]};base64,{img["data"]}" '
                        f'alt="Page {page["page_number"]} image" '
                        'style="max-width:100%; height:auto;">\n'
                    )

            # Add text content
            if page.get("text"):
                text_blocks = page["text"].split("\n\n")
                for block in text_blocks:
                    if block.strip():
                        page_html += f'<div class="text-block">{html.escape(block.strip()).replace("\n", "<br>")}</div>\n'

            page_html += "</div>\n"
            html_content += page_html

        return self.html_template.format(title=html.escape(title), content=html_content)

    def convert_pdf_to_html(
        self, pdf_path: str, output_path: str, title: str = None
    ) -> None:
        """Main method to convert PDF to HTML file"""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        if title is None:
            title = os.path.basename(pdf_path)

        try:
            pages_content = self.extract_pdf_content(pdf_path)
            html_content = self.convert_to_html(pages_content, title)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_content)

        except Exception as e:
            raise Exception(f"Error converting PDF to HTML: {str(e)}")


def main():
    converter = PDFToHTMLConverter()

    try:
        converter.convert_pdf_to_html(
            pdf_path="input.pdf",
            output_path="output.html",
            title="Converted PDF Document",
        )
        print("Conversion completed successfully!")

    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
