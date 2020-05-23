"""
Pulls crossword data from https://absite.ru/crossw/
"""
from io import BytesIO
import logging

from bs4 import BeautifulSoup
import cv2
import imutils
from imutils import contours
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import requests
from skimage import io


logger = logging.getLogger(__name__)


class Crossword:
    class _question:
        """A single crossword question with answer"""
        def __init__(self, num, q):
            self.id = num
            self.q = q
            self.ans = None
            self.start_cell = None

        def __str__(self):
            return f"{self.id}. {self.q}"

        def __repr__(self):
            return f"Question<{self.q} -> {self.ans}>"

    class _cell:
        """A single cell from crossword grid"""
        def __init__(self, cur_symbol=''):
            self.center = None
            self.symbol = cur_symbol
        
        def __repr__(self):
            return f"Cell<'{self.symbol}' at {self.center}>"
        
        def __str__(self):
            return self.symbol if self.symbol else ' '

    def __init__(self, cw_id):
        self.id = cw_id
        self.qs = dict()
        self.grid = None
        self.orig_im = None

        self._load_questions()
        self._get_img()
        self._prep_img()

    def _fill_answers(self, soup):
        ans_div = soup.find(
            lambda tag: (tag.name == u"h2" and u"hn" in tag.get("class", None)
                         and tag.string == u"Ответы на кроссворд")
        ).next_sibling.next_sibling.next_sibling.next_sibling
        div_children = list(ans_div.children)
        direction = "V"  # vertical
        if div_children[1].string == u"По горизонтали:":
            direction = "H"  # horizontal
        i = 4
        while i < len(div_children):
            if (i + 2 < len(div_children) and
                    div_children[i + 2].string in [u"По вертикали:", u"По горизонтали:"]):
                direction = "V" if u"По вертикали:" == div_children[i + 2].string else "H"
                i += 5
                continue
            num = div_children[i].string
            ans = div_children[i + 1].strip()
            self.qs[direction + num].ans = ans[2:len(ans) - 1]
            i += 2

    def _get_questions(self, soup):
        q_div = soup.find(
            lambda tag: (tag.name == u"h2" and u"hn" in tag.get("class", None)
                         and tag.string == u"Вопросы онлайн кроссворда")
        ).next_sibling.next_sibling
        for _ in range(2):
            div_children = list(q_div.children)
            direction = "V"  # vertical
            if div_children[1].string == u"По горизонтали:":
                direction = "H"  # horizontal
            for i in range(4, len(div_children), 4):
                num = div_children[i].string
                q_text = div_children[i + 1].strip()
                q = Crossword._question(num, q_text[2:len(q_text) - 1])
                self.qs[direction + num] = q
            q_div = q_div.next_sibling.next_sibling
        self._fill_answers(soup)

    def _get_img(self):
        print_link = f"https://absite.ru/crossw/{self.id}_pic.html"
        resp = requests.get(print_link)
        if resp.status_code != 200:
            raise requests.RequestException("Unable to load: {}".format(resp.status_code))
        soup = BeautifulSoup(resp.text, "html.parser")
        img = soup.find("img")
        img_link = "https://absite.ru/crossw/" + img.attrs["src"]
        self.orig_im = io.imread(img_link)

    def _load_questions(self):
        resp = requests.get("https://absite.ru/crossw/{}.html".format(self.id))
        if resp.status_code != 200:
            raise requests.RequestException("Unable to load: {}".format(resp.status_code))
        soup = BeautifulSoup(resp.text, "html.parser")
        self._get_questions(soup)

    def _prepare_grid(self, cell_cnts):
        largest_cell_dims = (0, 0, 0, 0)
        max_area = 0
        for cnt in cell_cnts:
            area = cv2.contourArea(cnt)
            if area > max_area:
                largest_cell_dims = cv2.boundingRect(cnt)
                max_area = area
        (x, y, w, h) = largest_cell_dims
        grid_x, grid_y = self.orig_im.shape[0] // w, self.orig_im.shape[1] // h
        self.grid = [[Crossword._cell() for _ in range(grid_x)] for _ in range(grid_y)]

    def _prep_img(self):
        orig = self.orig_im.copy()
        gray = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY)
        gray[gray == 76] = 0
        thresh = cv2.adaptiveThreshold(gray, 255, 1, 1, 11, 2)

        cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        mask = np.zeros((gray.shape), np.uint8)
        cv2.drawContours(mask, cnts, 0, 255, -1)

        internal = np.zeros_like(gray)
        internal[mask == 255] = gray[mask == 255]

        cnts, _ = cv2.findContours(internal.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        self._prepare_grid(cnts)
        for cnt in cnts:
            (x, y, w, h) = cv2.boundingRect(cnt)
            cnt_center = contour_center(cnt)
            grid_coords = im_to_grid_coords(
                cnt_center,
                (len(self.grid), len(self.grid[0])),
                self.orig_im.shape
            )
            self.grid[grid_coords[0]][grid_coords[1]].center = cnt_center
            inv_cell = cv2.bitwise_not(internal[y:y + h, x:x + w])
            symbols = cv2.findContours(inv_cell, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            symbols = imutils.grab_contours(symbols)

            digit_cnts = []
            for symb in symbols:
                (symb_x, symb_y, symb_w, symb_h) = cv2.boundingRect(symb)
                if symb_h == 7 and 4 >= symb_w > 1:
                    digit_cnts.append(symb)
                elif symb_h == 7 and symb_w > 4:
                    multisymb = inv_cell[symb_y:symb_y + symb_h, symb_x:symb_x + symb_w].copy()
                    multisymb[4, 4] = 0
                    if symb_w >= 10:
                        multisymb[4, 9] = 0
                    multisymb_split, _ = cv2.findContours(multisymb, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    for subsymb in multisymb_split:
                        digit_cnts.append(subsymb + np.array([symb_x, symb_y]))
            if not digit_cnts:
                continue

            digit_cnts = contours.sort_contours(digit_cnts, method="left-to-right")[0]
            cell_num = 0
            for digit_cnt in digit_cnts:
                (d_x, d_y, d_w, d_h) = cv2.boundingRect(digit_cnt)
                digit = inv_cell[d_y:d_y + d_h, d_x:d_x + d_w]
                value = img_to_number(digit)
                cell_num = cell_num * 10 + value
            for direction in ["H", "V"]:
                if self.qs.get(direction + str(cell_num)) is not None:
                    self.qs[direction + str(cell_num)].start_cell = grid_coords

    def cur_state(self):
        """
        Returns current crossword view as a byte matrix
        """
        cur_im = self.orig_im.copy()
        pil_img = Image.fromarray(cur_im, "RGBA")
        unicode_font = ImageFont.truetype("DejaVuSans.ttf", size=14)
        draw = ImageDraw.Draw(pil_img)
        for row in self.grid:
            for cell in row:
                if not cell.symbol or not cell.center:
                    continue
                text_size = unicode_font.getsize(cell.symbol)
                text_place = (cell.center[0] - text_size[0] // 2, cell.center[1] - text_size[1] // 2)
                draw.text(text_place, cell.symbol, font=unicode_font, fill=(0, 0, 0))
        cur_im = BytesIO()
        cur_im.name = 'cwrd.png'
        pil_img.save(cur_im, 'PNG')
        cur_im.seek(0)
        return cur_im

    def set_answer(self, question_id, answer):
        direction = question_id[0]
        question = self.qs[question_id]
        if len(answer) > len(question.ans):
            raise ValueError("Очень длинный ответ. Что-то здесь не так")
        x, y = question.start_cell
        for d, symb in enumerate(answer):
            if direction == 'H':
                self.grid[x + d][y].symbol = symb
            else:
                self.grid[x][y + d].symbol = symb

    def list_questions(self):
        hor_qs = "\n".join(map(lambda x: str(x[1]), sorted(
            filter(lambda x: x[0][0] == 'H', self.qs.items()),
            key=lambda x: int(x[1].id)
        )))
        vert_qs = "\n".join(map(lambda x: str(x[1]), sorted(
            filter(lambda x: x[0][0] == 'V', self.qs.items()),
            key=lambda x: int(x[1].id)
        )))
        return vert_qs, hor_qs

    @property
    def is_filled(self):
        result = True
        for row in self.grid:
            for cell in row:
                if cell.center and not cell.symbol:
                    result = False
        return result
    
    @property
    def is_solved(self):
        result = True
        for num, question in self.qs:
            x, y = question.start_cell
            for d, symb in enumerate(question.ans):
                result = result and symb == (
                    self.grid[x + d][y].symbol if num[0] == "H" else self.grid[x][y + d].symbol
                )
        return result


def img_to_number(digit):
    values = [
        np.array([[0, 1, 1, 0], [1, 0, 0, 1], [1, 0, 0, 1], [1, 0, 0, 1], [1, 0, 0, 1], [1, 0, 0, 1], [1, 1, 1, 0]], np.uint8),  # 0
        np.array([[0, 1]      , [1, 1]      , [0, 1]      , [0, 1]      , [0, 1]      , [0, 1]      , [0, 1]      ], np.uint8),  # 1
        np.array([[0, 1, 1, 0], [1, 0, 0, 1], [0, 0, 0, 1], [0, 0, 1, 0], [0, 0, 1, 0], [0, 1, 0, 0], [1, 1, 1, 1]], np.uint8),  # 2
        np.array([[0, 1, 1, 0], [1, 0, 0, 1], [0, 0, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1], [1, 0, 0, 1], [0, 1, 1, 0]], np.uint8),  # 3
        np.array([[0, 0, 0, 1], [0, 0, 1, 1], [0, 1, 0, 1], [1, 0, 0, 1], [1, 1, 1, 1], [0, 0, 0, 1], [0, 0, 0, 1]], np.uint8),  # 4
        np.array([[0, 1, 1, 1], [0, 1, 0, 0], [1, 1, 1, 0], [1, 0, 0, 1], [0, 0, 0, 1], [1, 0, 0, 1], [0, 1, 1, 0]], np.uint8),  # 5
        np.array([[0, 1, 1, 0], [1, 0, 0, 1], [1, 1, 1, 0], [1, 0, 0, 1], [1, 0, 0, 1], [1, 0, 0, 1], [0, 1, 1, 0]], np.uint8),  # 6
        np.array([[1, 1, 1, 1], [0, 0, 0, 1], [0, 0, 1, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 1, 0, 0], [0, 1, 0, 0]], np.uint8),  # 7
        np.array([[0, 1, 1, 0], [1, 0, 0, 1], [1, 0, 0, 1], [0, 1, 1, 0], [1, 0, 0, 1], [1, 0, 0, 1], [0, 1, 1, 0]], np.uint8),  # 8
        np.array([[0, 1, 1, 0], [1, 0, 0, 1], [1, 0, 0, 1], [1, 0, 0, 1], [0, 1, 1, 1], [1, 0, 0, 1], [0, 1, 1, 0]], np.uint8),  # 9
    ]
    digit = digit.copy()
    digit[digit == 255] = 1
    for value, value_image in enumerate(values):
        if value_image.shape == digit.shape and (value_image == digit).all():
            return value
    return 0

def contour_center(cnt):
    M = cv2.moments(cnt)
    x = int(M["m10"] / M["m00"])
    y = int(M["m01"] / M["m00"])
    return x, y

def im_to_grid_coords(point, grid_shape, im_shape):
    x_size, y_size = im_shape[0] / grid_shape[0], im_shape[1] / grid_shape[1]
    return int(point[0] / x_size), int(point[1] / y_size)


if __name__ == "__main__":
    cwrd = Crossword(179)
    print(*cwrd.list_questions())
    cwrd.set_answer("V3", "тандем")
    cur_state = cwrd.cur_state()
    with open("f.png", "wb") as f:
        f.write(cur_state.read())
