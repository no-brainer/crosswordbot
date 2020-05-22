"""
Pulls crossword data from https://absite.ru/crossw/
"""
from bs4 import BeautifulSoup
import cv2
import imutils
from imutils import contours
import numpy as np
import requests
from skimage import io


class Question:
    """A single crossword question with answer"""
    def __init__(self, direction, num, q):
        self.dir = direction
        self.id = num
        self.q = q
        self.ans = None

    def __str__(self):
        return f"{self.id}. {self.q}"

    def __repr__(self):
        return f"Question<{self.q} -> {self.ans}>"



class Crossword(object):
    def __init__(self, cw_id):
        self.id = cw_id
        self.hor_qs = []
        self.vert_qs = []
        self.numbered_cells = dict()

        self._load_questions()
        self._get_img_link()
        self._prep_img()

    def _fill_answers(self, soup, h_qs, v_qs):
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
            if direction == "H":
                if h_qs.get(num) is None:
                    raise Exception
                h_qs[num].ans = ans[2:len(ans) - 1]
            else:
                if v_qs.get(num) is None:
                    raise Exception
                v_qs[num].ans = ans[2:len(ans) - 1]
            i += 2

    def _get_questions(self, soup):
        h_qs = dict()
        v_qs = dict()

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
                q = Question(direction, num, q_text[2:len(q_text) - 1])
                if direction == "H":
                    h_qs[num] = q
                else:
                    v_qs[num] = q
            q_div = q_div.next_sibling.next_sibling
        self._fill_answers(soup, h_qs, v_qs)
        return h_qs, v_qs

    def _get_img_link(self):
        print_link = f"https://absite.ru/crossw/{self.id}_pic.html"
        resp = requests.get(print_link)
        if resp.status_code != 200:
            raise requests.RequestException("Unable to load: {}".format(resp.status_code))
        soup = BeautifulSoup(resp.text, "html.parser")
        img = soup.find("img")
        self.img_link = "https://absite.ru/crossw/" + img.attrs["src"]

    def _load_questions(self):
        resp = requests.get("https://absite.ru/crossw/{}.html".format(self.id))
        if resp.status_code != 200:
            raise requests.RequestException("Unable to load: {}".format(resp.status_code))

        soup = BeautifulSoup(resp.text, "html.parser")

        h_qs, v_qs = self._get_questions(soup)
        self.hor_qs = list(h_qs.values())
        self.vert_qs = list(v_qs.values())

    def _prep_img(self):
        orig = io.imread(self.img_link)
        gray = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY)
        gray[gray == 76] = 0
        thresh = cv2.adaptiveThreshold(gray, 255, 1, 1, 11, 2)

        cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        mask = np.zeros((gray.shape), np.uint8)
        cv2.drawContours(mask, cnts, 0, 255, -1)

        internal = np.zeros_like(gray)
        internal[mask == 255] = gray[mask == 255]

        cnts, _ = cv2.findContours(internal.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in cnts:
            (x, y, w, h) = cv2.boundingRect(cnt)
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
                # no possible digits in this cell
                continue

            digit_cnts = contours.sort_contours(digit_cnts, method="left-to-right")[0]
            cell_num = 0
            for digit_cnt in digit_cnts:
                (d_x, d_y, d_w, d_h) = cv2.boundingRect(digit_cnt)
                digit = inv_cell[d_y:d_y + d_h, d_x:d_x + d_w]
                value = img_to_number(digit)
                cell_num = cell_num * 10 + value
            self.numbered_cells[cell_num] = (x, y, w, h)


def img_to_number(digit):
    values = [
        np.array([[0, 1, 1, 0], [1, 0, 0, 1], [1, 0, 0, 1], [1, 0, 0, 1], [1, 0, 0, 1], [1, 0, 0, 1], [1, 1, 1, 0]], np.uint8),  # 0
        np.array([      [0, 1],       [1, 1],       [0, 1],       [0, 1],       [0, 1],       [0, 1],       [0, 1]], np.uint8),  # 1
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
    for i, value in enumerate(values):
        if value.shape == digit.shape and (value == digit).all():
            return i
    return 0


if __name__ == "__main__":
    cw = Crossword(179)
