"""
Pulls crossword data from https://absite.ru/crossw/
"""
from io import BytesIO
import logging
from random import randint

from bs4 import BeautifulSoup
import cv2
import imutils
from imutils import contours
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests
from skimage import io

import crossbot.settings as settings


logger = logging.getLogger(__name__)


class ParseException(Exception):
    pass


class Crossword:
    class _question:
        """A single crossword question with answer"""
        def __init__(self, num, q):
            self.id = num
            self.q = q
            self.ans = None
            self.start_cell = None
            self.is_attempted = False

        def __str__(self):
            ans_len = len(self.ans)
            conj = "букв"
            if ans_len // 10 != 1 and ans_len % 10 == 1:
                conj = "буква"
            elif ans_len // 10 != 1 and ans_len % 10 in [2, 3]:
                conj = "буквы"
            return f"{self.id}. {self.q} ({ans_len} {conj})"

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

        self._validate()

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
            ans = div_children[i + 1].strip().replace("ё", "e")
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

    def _prepare_grid(self, clean_grid_im):
        row_mask = np.sum(clean_grid_im, axis=0)
        col_mask = np.sum(clean_grid_im, axis=1)
        for mask in [row_mask, col_mask]:
            mask[mask != 0] = 1
            mask[:mask.argmax()] = 1
            last_one = len(mask) - np.flip(mask).argmax() - 1
            mask[last_one:] = 1
        grid_x = len(row_mask) - int(row_mask.sum()) + 1
        grid_y = len(col_mask) - int(col_mask.sum()) + 1
        self.grid = [[Crossword._cell() for _ in range(grid_x)] for _ in range(grid_y)]
        cnts, _ = cv2.findContours(np.outer(col_mask, row_mask).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in cnts:
            center = contour_center(cnt)
            x, y = point_to_grid_coords(center, row_mask, col_mask)
            self.grid[x][y].center = center
        return row_mask, col_mask

    def _prep_img(self):
        orig = self.orig_im.copy()
        gray = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY)
        gray[np.logical_and(gray != 0, gray != 255)] = 0
        thresh = cv2.adaptiveThreshold(gray, 255, 1, 1, 11, 2)

        cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        mask = np.zeros((gray.shape), np.uint8)
        cv2.drawContours(mask, cnts, 0, 255, -1)

        internal = np.zeros_like(gray)
        internal[mask == 255] = gray[mask == 255]

        row_mask, col_mask = self._prepare_grid(internal)

        cnts, _ = cv2.findContours(internal.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in cnts:
            (x, y, w, h) = cv2.boundingRect(cnt)
            inv_cell = cv2.bitwise_not(internal[y:y + h, x:x + w])
            # first things first, gotta take care of these nasty 4 so that digits are separated
            template = np.array(
                [[255, 0  ],
                 [255, 0  ],
                 [255, 0  ],
                 [255, 0  ],
                 [255, 255],
                 [255, 0  ],
                 [255, 0  ]],
                 np.uint8
            )
            result = cv2.matchTemplate(inv_cell, template, cv2.TM_CCOEFF_NORMED)
            loc = np.where(result >= 0.9)
            for point in zip(*loc[::-1]):
                inv_cell[point[1] + 4, point[0] + 1] = 0

            symbols = cv2.findContours(inv_cell, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            symbols = imutils.grab_contours(symbols)

            digit_cnts = []
            for symb in symbols:
                (_, _, symb_w, symb_h) = cv2.boundingRect(symb)
                if symb_h > 5 and symb_w > 1:
                    digit_cnts.append(symb)
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
                    center = contour_center(cnt)
                    grid_coords = point_to_grid_coords(center, row_mask, col_mask)
                    self.qs[direction + str(cell_num)].start_cell = grid_coords

    def _validate(self):
        for _, q in self.qs.items():
            if q.start_cell is None:
                raise ParseException()

    def cur_state(self):
        """
        Returns current crossword view as a byte matrix
        """
        cur_im = self.orig_im.copy()
        pil_img = Image.fromarray(cur_im, "RGBA")
        unicode_font = ImageFont.truetype("Arial.ttf", size=14)
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
        answer = answer.lower().replace("ё", "e")
        direction = question_id[0]
        question = self.qs[question_id]
        if len(answer) > len(question.ans):
            raise ValueError(settings.ANSWER_TOO_LONG_MSG)
        elif len(answer) < len(question.ans):
            raise ValueError(settings.ANSWER_TOO_SHORT_MSG)
        question.is_attempted = True
        x, y = question.start_cell
        for d, symb in enumerate(answer):
            if direction == 'H':
                self.grid[x + d][y].symbol = symb
            else:
                self.grid[x][y + d].symbol = symb

    def list_unattempted_questions(self):
        hor_qs = "\n".join(map(lambda x: str(x[1]), sorted(
            filter(lambda x: x[0][0] == 'H' and not x[1].is_attempted, self.qs.items()),
            key=lambda x: int(x[1].id)
        )))
        vert_qs = "\n".join(map(lambda x: str(x[1]), sorted(
            filter(lambda x: x[0][0] == 'V' and not x[1].is_attempted, self.qs.items()),
            key=lambda x: int(x[1].id)
        )))
        return vert_qs, hor_qs

    def list_unsolved_questions(self):
        all_unsolved = dict()
        for num, question in self.qs.items():
            is_solved = True
            x, y = question.start_cell
            for d, symb in enumerate(question.ans):
                cwrd_symb = (
                    self.grid[x + d][y].symbol if num[0] == "H" else self.grid[x][y + d].symbol
                )
                is_solved = is_solved and cwrd_symb == symb
            if not is_solved:
                all_unsolved[num] = question
        hor_qs = "\n".join(map(lambda x: str(x[1]), sorted(
            filter(lambda x: x[0][0] == 'H', all_unsolved),
            key=lambda x: int(x[1].id)
        )))
        vert_qs = "\n".join(map(lambda x: str(x[1]), sorted(
            filter(lambda x: x[0][0] == 'V', all_unsolved),
            key=lambda x: int(x[1].id)
        )))
        return vert_qs, hor_qs

    def complete_crossword(self):
        for num, q in self.qs.items():
            if not q.start_cell:
                continue
            x, y = q.start_cell
            for d, ans_symb in enumerate(q.ans):
                if num[0] == 'H':
                    self.grid[x + d][y].symbol = ans_symb
                else:
                    self.grid[x][y + d].symbol = ans_symb

    @property
    def is_filled(self):
        result = True
        for _, q in self.qs.items():
            result = result and q.is_attempted
        return result

    @property
    def is_solved(self):
        result = True
        for num, question in self.qs.items():
            x, y = question.start_cell
            for d, symb in enumerate(question.ans):
                cwrd_symb = (
                    self.grid[x + d][y].symbol if num[0] == "H" else self.grid[x][y + d].symbol
                )
                result = result and cwrd_symb == symb
        return result


def img_to_number(digit):
    digit = digit.copy()
    digit[digit == 255] = 1
    scores = []
    for value_template in settings.NUMBER_TEMPLATES:
        template = np.array(value_template, dtype=np.uint8)
        try:
            result = cv2.matchTemplate(digit, template, cv2.TM_CCOEFF_NORMED)
        except Exception:
            continue
        (_, score, _, _) = cv2.minMaxLoc(result)
        scores.append(score)
    return np.argmax(scores)

def contour_center(cnt):
    M = cv2.moments(cnt)
    x = int(M["m10"] / M["m00"])
    y = int(M["m01"] / M["m00"])
    return x, y

def point_to_grid_coords(point, grid_row_mask, grid_col_mask):
    x = point[0] - int(grid_row_mask[:point[0]].sum())
    y = point[1] - int(grid_col_mask[:point[1]].sum())
    return x, y

if __name__ == "__main__":
    for _ in range(10):
        try:
            cwrd = Crossword(randint(1, 5000))
        except Exception:
            continue
        cwrd.complete_crossword()
        cur_state = cwrd.cur_state()
        with open(f"f{cwrd.id}.png", "wb") as f:
            f.write(cur_state.read())
