"""Bounded, inert HTML trees for exported tables and public event markup."""
from html.parser import HTMLParser

class Node:
    def __init__(self, tag="", attrs=()):
        self.tag=tag
        self.attrs=dict(attrs)
        self.children=[]
    def text(self):
        return " ".join(" ".join(c.text() if isinstance(c,Node) else c for c in self.children).split())
    def find(self, tag=None, **attrs):
        for c in self.children:
            if not isinstance(c,Node):
                continue
            if (tag is None or c.tag==tag) and all(
                v in c.attrs.get(k,"").split() for k,v in attrs.items()):
                yield c
            yield from c.find(tag,**attrs)

class Tree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        if len(html)>8_000_000:
            raise ValueError("HTML exceeds the bounded reading limit.")
        self.root=Node()
        self.stack=[self.root]
        self.feed(html)
    def handle_starttag(self,tag,attrs):
        n=Node(tag,attrs)
        self.stack[-1].children.append(n)
        if tag not in {"br","hr","img","meta","link","input","wbr","source","area","base","embed","param","col"}:
            if len(self.stack)>100:
                raise ValueError("HTML nesting limit exceeded.")
            self.stack.append(n)
        elif tag=="br":
            self.stack[-1].children.append(" ")
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:
                self.stack=self.stack[:i]
                break
    def handle_data(self,text):
        if not any(n.tag in {"script","style"} for n in self.stack):
            self.stack[-1].children.append(text)

def table_rows(html):
    tree=Tree(html)
    return [[c.text() for c in tr.children if isinstance(c,Node) and c.tag in {"th","td"}]
            for tr in tree.root.find("tr")]
