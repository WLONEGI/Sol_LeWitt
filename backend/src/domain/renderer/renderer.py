"""
PPTXファイルをPNG画像にレンダリングするユーティリティ。

依存関係:
- LibreOffice (soffice コマンド)
- Poppler (pdf2image が内部で使用)
- pdf2image (pip install pdf2image)
"""
import asyncio
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from pdf2image import convert_from_path
from pdf2image.exceptions import PDFPageCountError

logger = logging.getLogger(__name__)


@dataclass
class RenderedSlide:
    """レンダリングされたスライド1枚分のデータ"""
    slide_number: int
    image_bytes: bytes
    width: int
    height: int


class PPTXRenderer:
    """PPTXをPNG画像にレンダリングするクラス
    
    LibreOffice headlessモードでPPTXをPDFに変換し、
    pdf2imageでPNGに変換する2段階処理を行う。
    """
    
    def __init__(
        self, 
        dpi: int = 150,
        timeout_seconds: int = 60,
        libreoffice_path: Optional[str] = None
    ):
        """
        Args:
            dpi: レンダリング解像度（デフォルト: 150）
            timeout_seconds: LibreOffice変換のタイムアウト秒数
            libreoffice_path: LibreOffice実行ファイルのパス（Noneの場合は自動検出）
        """
        self.dpi = dpi
        self.timeout_seconds = timeout_seconds
        self.libreoffice_path = libreoffice_path or self._find_libreoffice()
    
    def _find_libreoffice(self) -> str:
        """LibreOfficeの実行パスを検出
        
        Returns:
            str: LibreOfficeの実行パス
            
        Raises:
            RuntimeError: LibreOfficeが見つからない場合
        """
        candidates = [
            "/usr/bin/soffice",
            "/usr/bin/libreoffice",
            "/opt/libreoffice/program/soffice",
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "soffice",
        ]
        for path in candidates:
            try:
                result = subprocess.run(
                    [path, "--version"], 
                    capture_output=True, 
                    timeout=5
                )
                if result.returncode == 0:
                    logger.info(f"LibreOffice found at: {path}")
                    return path
            except (subprocess.SubprocessError, FileNotFoundError):
                continue
        
        raise RuntimeError(
            "LibreOffice not found. Please install LibreOffice. "
            "On macOS: brew install --cask libreoffice, "
            "On Ubuntu: apt install libreoffice-impress"
        )
    
    async def render_to_png(
        self, 
        pptx_bytes: bytes,
        max_slides: Optional[int] = None
    ) -> List[RenderedSlide]:
        """PPTXバイトデータを各スライドのPNG画像に変換
        
        Args:
            pptx_bytes: PPTXファイルのバイトデータ
            max_slides: レンダリングする最大スライド数（Noneの場合は全て）
            
        Returns:
            List[RenderedSlide]: レンダリングされたスライドのリスト
            
        Raises:
            RuntimeError: PDF変換に失敗した場合
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Step 1: PPTXを一時ファイルに保存
            pptx_path = tmpdir_path / "input.pptx"
            pptx_path.write_bytes(pptx_bytes)
            logger.info(f"PPTX saved to temp: {pptx_path}")
            
            # Step 2: LibreOffice でPDFに変換
            pdf_path = await self._convert_to_pdf(pptx_path, tmpdir_path)
            if not pdf_path:
                raise RuntimeError("PDF conversion failed")
            
            # Step 3: pdf2image でPNGに変換
            slides = await self._convert_pdf_to_images(pdf_path, max_slides)
            logger.info(f"Rendered {len(slides)} slides to PNG")
            
            return slides
    
    async def _convert_to_pdf(
        self, pptx_path: Path, output_dir: Path
    ) -> Optional[Path]:
        """LibreOffice headless でPPTXをPDFに変換
        
        Args:
            pptx_path: PPTXファイルのパス
            output_dir: 出力ディレクトリ
            
        Returns:
            Optional[Path]: 生成されたPDFのパス、失敗した場合はNone
        """
        cmd = [
            self.libreoffice_path,
            "--headless", "--invisible", "--nologo", "--nofirststartwizard",
            "--convert-to", "pdf",
            "--outdir", str(output_dir),
            str(pptx_path)
        ]
        
        try:
            logger.info(f"Running LibreOffice: {' '.join(cmd)}")
            result = await asyncio.to_thread(
                subprocess.run, cmd,
                capture_output=True, timeout=self.timeout_seconds, cwd=str(output_dir)
            )
            
            if result.returncode != 0:
                logger.error(f"LibreOffice failed: {result.stderr.decode()}")
                return None
            
            # 出力PDFを探す
            pdf_path = output_dir / "input.pdf"
            if pdf_path.exists():
                logger.info(f"PDF created: {pdf_path}")
                return pdf_path
            
            # 別の名前でPDFが作成された場合
            pdf_files = list(output_dir.glob("*.pdf"))
            if pdf_files:
                logger.info(f"PDF found: {pdf_files[0]}")
                return pdf_files[0]
            
            logger.error("No PDF file found after conversion")
            return None
            
        except subprocess.TimeoutExpired:
            logger.error(f"LibreOffice timed out after {self.timeout_seconds}s")
            return None
        except Exception as e:
            logger.error(f"LibreOffice conversion error: {e}")
            return None
    
    async def _convert_pdf_to_images(
        self, pdf_path: Path, max_slides: Optional[int] = None
    ) -> List[RenderedSlide]:
        """pdf2image でPDFの各ページをPNG画像に変換
        
        Args:
            pdf_path: PDFファイルのパス
            max_slides: 変換する最大ページ数
            
        Returns:
            List[RenderedSlide]: レンダリングされたスライドのリスト
        """
        try:
            logger.info(f"Converting PDF to images: {pdf_path}")
            images = await asyncio.to_thread(
                convert_from_path,
                str(pdf_path),
                dpi=self.dpi,
                fmt='png',
                thread_count=2,
                first_page=1,
                last_page=max_slides if max_slides else None
            )
            
            slides: List[RenderedSlide] = []
            for i, img in enumerate(images, start=1):
                buffer = BytesIO()
                img.save(buffer, format='PNG', optimize=True)
                buffer.seek(0)
                
                slides.append(RenderedSlide(
                    slide_number=i,
                    image_bytes=buffer.getvalue(),
                    width=img.width,
                    height=img.height
                ))
                logger.debug(f"Slide {i} rendered: {img.width}x{img.height}")
            
            return slides
            
        except PDFPageCountError as e:
            logger.error(f"PDF page count error: {e}")
            return []
        except Exception as e:
            logger.error(f"PDF to image conversion error: {e}")
            return []


async def render_first_slide(pptx_bytes: bytes, dpi: int = 150) -> Optional[bytes]:
    """PPTXの最初のスライドをPNG画像としてレンダリング
    
    Args:
        pptx_bytes: PPTXファイルのバイトデータ
        dpi: レンダリング解像度
        
    Returns:
        Optional[bytes]: 最初のスライドのPNG画像バイトデータ、失敗した場合はNone
    """
    try:
        renderer = PPTXRenderer(dpi=dpi)
        slides = await renderer.render_to_png(pptx_bytes, max_slides=1)
        return slides[0].image_bytes if slides else None
    except Exception as e:
        logger.error(f"render_first_slide failed: {e}")
        return None


async def render_all_slides(pptx_bytes: bytes, dpi: int = 150) -> List[RenderedSlide]:
    """PPTXの全スライドをPNG画像としてレンダリング
    
    Args:
        pptx_bytes: PPTXファイルのバイトデータ
        dpi: レンダリング解像度
        
    Returns:
        List[RenderedSlide]: レンダリングされたスライドのリスト
    """
    try:
        renderer = PPTXRenderer(dpi=dpi)
        return await renderer.render_to_png(pptx_bytes)
    except Exception as e:
        logger.error(f"render_all_slides failed: {e}")
        return []
