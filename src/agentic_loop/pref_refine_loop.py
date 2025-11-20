import os
import json
import shutil
from utils import pjoin
from presentation import Presentation

from .loop_utils import get_file_name_hash

from stage_modules import (
    stage_ppt_template_parsing,
    stage_slide_induction,
    stage_reference_document_parsing,
    stage_target_document_parsing,
    stage_presentation_generation,
    stage_presentation_refinement,
)


def refine_loop_with_cache(
    ppt_path,
    ref_content_pdf,
    ref_content_ppt,
    target_pdf,
    args,
    project_id,
    output_dir,
    generation_config,
    pptx_config,
    vision_model,
    language_model,
    text_model,
    image_model,
    marker_model,
    use_cache=True,
    renew_cache=True,
    cache_dir="runs/cache"
):
    """
    Execute the sequence of stages for presentation generation and refinement in a linear flow with caching.
    
    Args:
        ppt_path (str): Path to the PowerPoint template
        ref_content_pdf (str): Path to the reference PDF
        ref_content_ppt (str): Path to the reference PPT
        target_pdf (str): Path to the target PDF to convert
        args (argparse.Namespace): Command line arguments
        project_id (str): Unique project ID
        output_dir (str): ProjectOutput directory
        generation_config (Config): Configuration for generation
        pptx_config (Config): Configuration for the PPTX
        vision_model (LLM): Vision model
        language_model (LLM): Language model
        text_model (BGEM3FlagModel): Text embedding model
        image_model: Image model
        marker_model: Marker model
        use_cache (bool): Whether to use and update the cache
        renew_cache (bool): Whether to renew cache even if it exists
        cache_dir (str): Path to the cache directory
    Returns:
        str: Path to the final refined presentation
    """

    
    # Create cache directories if they don't exist
    os.makedirs(pjoin(cache_dir, "pptx"), exist_ok=True)
    os.makedirs(pjoin(cache_dir, "pdf"), exist_ok=True)
    
    # Copy template to the project directory
    if not os.path.exists(pjoin(pptx_config.RUN_DIR, "source.pptx")):
        os.system(f"cp '{ppt_path}' '{pjoin(pptx_config.RUN_DIR, 'source.pptx')}'")
    
    # 1. PPT template parsing with caching
    print("[STAGE] PPT Template Parsing")
    ppt_hash = get_file_name_hash(ppt_path, prefix="pptx_")
    ppt_cache_dir = pjoin(cache_dir, "pptx", ppt_hash)
    
    if use_cache and os.path.exists(ppt_cache_dir) and os.path.exists(pjoin(ppt_cache_dir, "slide_images")):
        print(f"[CACHE] Using cached PPT template parsing from {ppt_cache_dir}")
        # Load presentation from cache
        presentation = Presentation.from_file(pjoin(ppt_cache_dir, "source.pptx"), pptx_config)
        ppt_image_folder = pjoin(ppt_cache_dir, "slide_images")
        
        # Copy cached files to the project directory for this run
        if not os.path.exists(pjoin(pptx_config.RUN_DIR, "slide_images")):
            shutil.copytree(ppt_image_folder, pjoin(pptx_config.RUN_DIR, "slide_images"))
    else:
        # Run template parsing and cache results
        presentation, ppt_image_folder = stage_ppt_template_parsing(
            pjoin(pptx_config.RUN_DIR, "source.pptx"),
            pptx_config,
            vision_model
        )
        
        # Cache the results
        if renew_cache:
            os.makedirs(ppt_cache_dir, exist_ok=True)
            # Copy the everything in pptx_config.RUN_DIR to ppt_cache_dir
            shutil.copytree(pptx_config.RUN_DIR, ppt_cache_dir, dirs_exist_ok=True)
            
            # Save the presentation explicitly
            shutil.copy(pjoin(pptx_config.RUN_DIR, "source.pptx"), pjoin(ppt_cache_dir, "source.pptx"))
            
            # Ensure the image directory exists in the cache
            if os.path.exists(ppt_image_folder):
                slide_images_cache_dir = pjoin(ppt_cache_dir, "slide_images")
                shutil.copytree(ppt_image_folder, slide_images_cache_dir, dirs_exist_ok=True)
            else:
                print("[WARNING] slide_images directory not found, cache may be incomplete")
    
    # 2. Slide induction (template analysis) with caching
    print("[STAGE] Slide Induction")
    induction_cache_dir = pjoin(cache_dir, "pptx", ppt_hash, "induction")
    
    if use_cache and os.path.exists(induction_cache_dir) and os.path.exists(pjoin(induction_cache_dir, "slide_induction.json")) and os.path.exists(pjoin(induction_cache_dir, "template.pptx")):
        print(f"[CACHE] Using cached slide induction from {induction_cache_dir}")
        # Load template presentation and slide induction from cache
        template_presentation = Presentation.from_file(pjoin(induction_cache_dir, "template.pptx"), pptx_config)
        with open(pjoin(induction_cache_dir, "slide_induction.json"), "r") as f:
            slide_induction = json.load(f)
            
        # Copy cached files to the project directory
        if not os.path.exists(pjoin(pptx_config.RUN_DIR, "template.pptx")):
            shutil.copy(pjoin(induction_cache_dir, "template.pptx"), pjoin(pptx_config.RUN_DIR, "template.pptx"))
        if not os.path.exists(pjoin(pptx_config.RUN_DIR, "slide_induction.json")):
            shutil.copy(pjoin(induction_cache_dir, "slide_induction.json"), pjoin(pptx_config.RUN_DIR, "slide_induction.json"))
    else:
        from model_utils import get_image_model
        image_model = get_image_model(device=args.device)
        
        # Run slide induction
        template_presentation, slide_induction = stage_slide_induction(
            presentation,
            ppt_image_folder,
            pptx_config,
            vision_model,
            language_model,
            image_model
        )
        
        # Cache the results
        if use_cache:
            os.makedirs(induction_cache_dir, exist_ok=True)
            # Save template presentation
            if os.path.exists(pjoin(pptx_config.RUN_DIR, "template.pptx")):
                shutil.copy(pjoin(pptx_config.RUN_DIR, "template.pptx"), pjoin(induction_cache_dir, "template.pptx"))
            # Save slide induction
            with open(pjoin(induction_cache_dir, "slide_induction.json"), "w") as f:
                json.dump(slide_induction, f, indent=2)
    
    
    # import pdb; pdb.set_trace()
    
    # 3. Reference document parsing with caching
    print("[STAGE] Reference Document Parsing")
    ref_pdf_hash = get_file_name_hash(ref_content_pdf, prefix="refpdf_")
    ref_ppt_hash = get_file_name_hash(ref_content_ppt, prefix="refppt_")
    ref_cache_dir = pjoin(cache_dir, "sample_pair", f"{ref_pdf_hash}_{ref_ppt_hash}")
    
    if use_cache and os.path.exists(ref_cache_dir) and os.path.exists(pjoin(ref_cache_dir, "pref_guidelines.json")):
        print(f"[CACHE] Using cached reference document parsing from {ref_cache_dir}")
        # Load preference guidelines from cache
        with open(pjoin(ref_cache_dir, "pref_guidelines.json"), "r") as f:
            pref_guidelines = json.load(f)
            
        # Copy to project directory
        pref_guidelines_path = pjoin(output_dir, "pref_guidelines.json")
        with open(pref_guidelines_path, "w") as f:
            json.dump(pref_guidelines, f, indent=2)

    else:
        from marker.models import create_model_dict
        import torch
        marker_model = create_model_dict(device=args.device, dtype=torch.float16)
        
        # Run reference document parsing
        pref_guidelines = stage_reference_document_parsing(
            ref_content_pdf,
            ref_content_ppt,
            marker_model,
            vision_model,
            language_model,
            project_id
        )

        # Cache the results
        if use_cache:
            os.makedirs(ref_cache_dir, exist_ok=True)
            with open(pjoin(ref_cache_dir, "pref_guidelines.json"), "w") as f:
                json.dump(pref_guidelines, f, indent=2)
            
            # Copy parsed PDFs to cache if they exist
            ref_pdf_dir = pjoin("runs", project_id, "pdf", "ref_pdf")
            ref_ppt_dir = pjoin("runs", project_id, "pdf", "ref_slide_pdf")
            
            if os.path.exists(ref_pdf_dir):
                os.makedirs(pjoin(ref_cache_dir, "ref_pdf"), exist_ok=True)
                for file in os.listdir(ref_pdf_dir):
                    shutil.copy(pjoin(ref_pdf_dir, file), pjoin(ref_cache_dir, "ref_pdf", file))
                    
            if os.path.exists(ref_ppt_dir):
                os.makedirs(pjoin(ref_cache_dir, "ref_slide_pdf"), exist_ok=True)
                for file in os.listdir(ref_ppt_dir):
                    shutil.copy(pjoin(ref_ppt_dir, file), pjoin(ref_cache_dir, "ref_slide_pdf", file))
    
    # 4. Target document parsing with caching
    print("[STAGE] Target Document Parsing")
    target_pdf_hash = get_file_name_hash(target_pdf, prefix="tgtpdf_")
    target_cache_dir = pjoin(cache_dir, "pdf", target_pdf_hash)
    
    if use_cache and os.path.exists(target_cache_dir) and os.path.exists(pjoin(target_cache_dir, "refined_doc.json")) and os.path.exists(pjoin(target_cache_dir, "image_captions.json")):
        print(f"[CACHE] Using cached target document parsing from {target_cache_dir}")
        # Load document JSON and images from cache
        with open(pjoin(target_cache_dir, "refined_doc.json"), "r") as f:
            doc_json = json.load(f)
        with open(pjoin(target_cache_dir, "image_captions.json"), "r") as f:
            images = json.load(f)
            
        # Copy to project directory
        target_dir = pjoin("runs", project_id, "pdf", "target_pdf")
        os.makedirs(target_dir, exist_ok=True)
        with open(pjoin(target_dir, "refined_doc.json"), "w") as f:
            json.dump(doc_json, f, indent=2)
        with open(pjoin(target_dir, "image_captions.json"), "w") as f:
            json.dump(images, f, indent=2)
            
        # Copy images if they exist
        if os.path.exists(pjoin(target_cache_dir, "images")):
            os.makedirs(pjoin(target_dir, "images"), exist_ok=True)
            for img_file in os.listdir(pjoin(target_cache_dir, "images")):
                shutil.copy(pjoin(target_cache_dir, "images", img_file), pjoin(target_dir, "images", img_file))
    else:
        
        from marker.models import create_model_dict
        import torch
        marker_model = create_model_dict(device=args.device, dtype=torch.float16)
        
        # Run target document parsing
        doc_json, images = stage_target_document_parsing(
            target_pdf,
            marker_model,
            vision_model,
            language_model,
            project_id,
            pref_guidelines
        )
        
        # Cache the results
        if use_cache:
            os.makedirs(target_cache_dir, exist_ok=True)
            with open(pjoin(target_cache_dir, "refined_doc.json"), "w") as f:
                json.dump(doc_json, f, indent=2)
            with open(pjoin(target_cache_dir, "image_captions.json"), "w") as f:
                # redirect the images from the target_dir to the cache
                redir_images = {}
                for k, v in images.items():
                    redir_images[os.path.join(target_cache_dir, "images", os.path.basename(k))] = v
                images = redir_images
                json.dump(images, f, indent=2)
                
            # Copy images to cache
            target_dir = pjoin("runs", project_id, "pdf", "target_pdf")
            if os.path.exists(target_dir):
                for file in os.listdir(target_dir):
                    if file.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                        os.makedirs(pjoin(target_cache_dir, "images"), exist_ok=True)
                        shutil.copy(pjoin(target_dir, file), pjoin(target_cache_dir, "images", file))
    
    # import pdb; pdb.set_trace()
    
    # 5. Initial presentation generation
    print("[STAGE] Initial PPT Generation")
    
    # Combine all hashes to create a unique identifier for this generation
    slides_count_hash = f"slides_{args.slides}"
    gen_hash = f"{ppt_hash}_{ref_pdf_hash}_{ref_ppt_hash}_{target_pdf_hash}_{slides_count_hash}"
    gen_cache_dir = pjoin(cache_dir, "generation", gen_hash)
    cached_pptx_path = pjoin(gen_cache_dir, "final.pptx")
    cached_outline_path = pjoin(gen_cache_dir, "presentation_outline.json")
    
    # if have a cached generation result
    if use_cache and not args.regen_outline and os.path.exists(gen_cache_dir) and os.path.exists(cached_pptx_path) and os.path.exists(cached_outline_path):
        print(f"[CACHE] Using cached presentation generation from {gen_cache_dir}")
        
        # Copy the cached presentation to the output directory
        output_pptx_path = pjoin(output_dir, "final.pptx")
        shutil.copy(cached_pptx_path, output_pptx_path)
        
        # Convert to PDF if needed
        if not os.path.exists(output_pptx_path.replace(".pptx", ".pdf")):
            from utils import pptx_to_pdf
            pptx_to_pdf(output_pptx_path, output_dir)
            
        initial_pptx_path = output_pptx_path
        with open(pjoin(gen_cache_dir, "presentation_outline.json"), "r") as f:
            presentation_outline = json.load(f)
        shutil.copy(pjoin(gen_cache_dir, "presentation_outline.json"), pjoin(output_dir, "presentation_outline.json"))
            
    else:
        
        from model_utils import get_text_model
        text_model = get_text_model(device=args.device)
        
        print("[INFO] Generating presentation outline")
        
        # Generate the presentation
        initial_pptx_path, presentation_outline = stage_presentation_generation(
            template_presentation=template_presentation,
            slide_induction=slide_induction,
            generation_config=generation_config,
            pref_guidelines=pref_guidelines,
            images=images,
            num_slides=args.slides,
            doc_json=doc_json,
            vision_model=vision_model,
            language_model=language_model,
            text_model=text_model
        )
        
        # Cache the generated presentation
        if use_cache and initial_pptx_path is not None:
            os.makedirs(gen_cache_dir, exist_ok=True)
            
            # Copy the generated presentation to the cache
            shutil.copy(initial_pptx_path, cached_pptx_path)
            
            # Copy PDF if it exists
            pdf_path = initial_pptx_path.replace(".pptx", ".pdf")
            if os.path.exists(pdf_path):
                shutil.copy(pdf_path, pjoin(gen_cache_dir, "final.pdf"))
            
            # Copy presentation outline to cache
            with open(pjoin(gen_cache_dir, "presentation_outline.json"), "w") as f:
                json.dump(presentation_outline, f, indent=2)
    
    # Skip refinement if requested or if initial generation failed
    if not hasattr(args, 'no_refinement') or args.no_refinement or initial_pptx_path is None:
        if initial_pptx_path is None:
            print("[ERROR] Initial presentation generation failed. Skipping refinement.")
            return None
        else:
            print("[INFO] Refinement disabled. Using initial presentation.")
            return initial_pptx_path
    
    # import pdb; pdb.set_trace()
    # ensure till now everything need is copied from cache to the project directory
    
    # 6. Refinement process **(NO Caching)**
    print("[STAGE] Refinement Process")
    
    final_pptx_path = stage_presentation_refinement(
        initial_pptx_path=initial_pptx_path,
        ref_ppt_path=ref_content_ppt,
        generation_config=generation_config,
        pptx_config=pptx_config,
        doc_json=doc_json,
        template_presentation=template_presentation,
        slide_induction=slide_induction,
        presentation_outline=presentation_outline,
        pref_guidelines=pref_guidelines,
        images=images,
        num_slides=args.slides,
        vision_model=vision_model,
        language_model=language_model,
        text_model=text_model,
        project_id=project_id,
        max_refine_iterations=args.iterations
    )

    
    print("[INFO] Refinement process complete!")
    return final_pptx_path


def refine_loop(
    ppt_path,
    ref_content_pdf,
    ref_content_ppt,
    target_pdf,
    args,
    project_id,
    output_dir,
    generation_config,
    pptx_config,
    vision_model,
    language_model,
    text_model,
    image_model,
    marker_model,
):
    """
    Execute the sequence of stages for presentation generation and refinement in a linear flow.
    
    Args:
        ppt_path (str): Path to the PowerPoint template
        ref_content_pdf (str): Path to the reference PDF
        ref_content_ppt (str): Path to the reference PPT
        target_pdf (str): Path to the target PDF to convert
        args (argparse.Namespace): Command line arguments
        project_id (str): Unique project ID
        output_dir (str): Output directory
        generation_config (Config): Configuration for generation
        pptx_config (Config): Configuration for the PPTX
        vision_model (LLM): Vision model
        language_model (LLM): Language model
        text_model (BGEM3FlagModel): Text embedding model
        image_model: Image model
        marker_model: Marker model
        
    Returns:
        str: Path to the final refined presentation
    """
    
    # Copy template
    if not os.path.exists(pjoin(pptx_config.RUN_DIR, "source.pptx")):
        os.system(f"cp '{ppt_path}' '{pjoin(pptx_config.RUN_DIR, 'source.pptx')}'")
    
    # 1. PPT template parsing
    print("[STAGE] PPT Template Parsing")
    presentation, ppt_image_folder = stage_ppt_template_parsing(
        pjoin(pptx_config.RUN_DIR, "source.pptx"),
        pptx_config,
        vision_model
    )
    
    # 2. Slide induction (template analysis)
    print("[STAGE] Slide Induction")
    template_presentation, slide_induction = stage_slide_induction(
        presentation,
        ppt_image_folder,
        pptx_config,
        vision_model,
        language_model,
        image_model
    )
    
    # 3. Reference document parsing
    print("[STAGE] Reference Document Parsing")
    pref_guidelines = stage_reference_document_parsing(
        ref_content_pdf,
        ref_content_ppt,
        marker_model,
        vision_model,
        language_model,
        project_id
    )
    
    # 4. Target document parsing
    print("[STAGE] Target Document Parsing")
    doc_json, images = stage_target_document_parsing(
        target_pdf,
        marker_model,
        vision_model,
        language_model,
        project_id,
        pref_guidelines
    )
    
    # 5. Initial presentation generation
    print("[STAGE] Initial PPT Generation")
    initial_pptx_path = stage_presentation_generation(
        template_presentation,
        slide_induction,
        generation_config,
        pref_guidelines,
        images,
        args.slides,
        doc_json,
        vision_model,
        language_model,
        text_model
    )
    
    # Skip refinement if requested or if initial generation failed
    if args.no_refinement or initial_pptx_path is None:
        if initial_pptx_path is None:
            print("[ERROR] Initial presentation generation failed. Skipping refinement.")
            return None
        else:
            print("[INFO] Refinement disabled. Using initial presentation.")
            return initial_pptx_path
    
    
    # 6. Refinement process
    print("[STAGE] Refinement Process")
    
    final_pptx_path = stage_presentation_refinement(
        initial_pptx_path,
        ref_content_ppt,
        generation_config,
        pptx_config,
        doc_json,
        template_presentation,
        slide_induction,
        pref_guidelines,
        images,
        args.slides,
        vision_model,
        language_model,
        text_model,
        image_model,
        marker_model,
        args.device,
        project_id=project_id,
        max_refine_iterations=args.iterations
    )
    
    print("[INFO] Refinement process complete!")
    return final_pptx_path