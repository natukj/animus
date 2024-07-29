from typing import Union, Any, Dict
from fastapi import UploadFile
import parsers, utils

class PDFParserRouter:
    def __init__(self, output_dir, file_name, checkpoint, verbose):
        self.output_dir = output_dir
        self.file_name = file_name
        self.checkpoint = checkpoint
        self.verbose = verbose
        self.toc_parser = None
        self.adapter_type = None
        self.adapters = {
            "VarTextSize": parsers.VarTextSizeAdapter,
            "SameTextSize": parsers.SameTextSizeAdapter
        }

    async def parse(self, file: Union[UploadFile, str]) -> Dict[str, Any]:
        if not self.adapter_type:
            await self.get_adapter(file)
        if self.adapter_type not in self.adapters:
            raise ValueError(f"Invalid parser type: {self.adapter_type}")
        specific_adapter_class = self.adapters[self.adapter_type]
        specific_adapter = specific_adapter_class(
            self.toc_parser, 
            self.output_dir, 
            self.checkpoint, 
            self.verbose
        )
        if self.verbose:
            utils.print_coloured(f"Using adapter: {specific_adapter_class.__name__}", "green")
        
        return await specific_adapter.parse()
    
    async def get_adapter(self, file: Union[UploadFile, str]) -> str:
        self.toc_parser = parsers.PDFToCParser(
            file, 
            self.output_dir, 
            self.file_name, 
            self.checkpoint, 
            self.verbose
        )
        self.adapter_type = await self.toc_parser.determine_toc_structure()